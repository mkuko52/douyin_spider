"""signer.py —— Python → Node 参数生成桥。

约定（本项目自包含，不读本机环境变量）：

- Node 用 **项目自带** `runtime/node_local/node.exe`（Node 22，nv8 要求）；
  可用 `SIGNER_NODE` 覆盖。
- 常驻一个 Node 子进程（`node/signer_server.mjs`），走 JSON-Lines over stdio，
  避免每次请求都重新起 nv8 沙箱。
- Node 只生成参数（dtrait payload / a_bogus），**不发网络**；
  最终 HTTP 出口由 Python 独占（见 Non-Negotiables）。
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_JS = PROJECT_ROOT / "node" / "signer_server.mjs"
LOCAL_NODE = PROJECT_ROOT / "runtime" / "node_local" / "node.exe"

# dtrait payload 磁盘缓存：设备指纹是稳定的，页面在同一会话里也复用它。
# 首次生成要启 Node + nv8 沙箱（~4.7s），缓存后 0 开销。
DTRAIT_CACHE = PROJECT_ROOT / "js_reverse_cache" / "private" / "dtrait_payload_cache.json"
DTRAIT_TTL = float(os.environ.get("DTRAIT_TTL", "86400"))   # 秒，默认 24h


def _read_dtrait_cache() -> dict | None:
    try:
        if DTRAIT_CACHE.exists() and (time.time() - DTRAIT_CACHE.stat().st_mtime) <= DTRAIT_TTL:
            data = json.loads(DTRAIT_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("str"):
                return data
    except Exception:
        pass
    return None


def _write_dtrait_cache(payload: dict) -> None:
    try:
        DTRAIT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        DTRAIT_CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

if not LOCAL_NODE.exists():  # 非 Windows 或未建 junction 时的兜底
    LOCAL_NODE = PROJECT_ROOT / "runtime" / "node_local" / "bin" / "node"


class SignerError(RuntimeError):
    pass


def _node_path() -> Path:
    import os

    override = os.environ.get("SIGNER_NODE")
    node = Path(override) if override else LOCAL_NODE
    if not node.exists():
        raise SignerError(
            "找不到项目自带 Node：%s\n请先执行：runtime\\venv\\Scripts\\python.exe runtime\\bootstrap.py --install" % node
        )
    return node


class NodeSigner:
    """常驻 Node 参数生成服务（线程安全）。"""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._seq = 0
        self._dtrait: dict | None = None

    # ---------------------------------------------------------------- 进程
    def _start(self) -> subprocess.Popen:
        if self._proc and self._proc.poll() is None:
            return self._proc
        proc = subprocess.Popen(
            [str(_node_path()), str(SERVER_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(PROJECT_ROOT),
        )
        ready = proc.stdout.readline()
        if not ready or "ready" not in ready:
            raise SignerError("Node 参数服务启动失败: %r" % ready)
        self._proc = proc
        return proc

    def close(self) -> None:
        """幂等：可被调用多次。"""
        if self._proc is None:
            return
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.close()
                    self._proc.wait(timeout=10)
                except Exception:
                    self._proc.kill()
            if self._proc:
                for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                    try:
                        if stream and not stream.closed:
                            stream.close()
                    except Exception:
                        pass
            self._proc = None

    def _call(self, cmd: str, **payload: Any) -> dict:
        with self._lock:
            proc = self._start()
            self._seq += 1
            req = {"id": self._seq, "cmd": cmd}
            req.update(payload)
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
            if not line:
                raise SignerError("Node 参数服务无响应（cmd=%s）" % cmd)
            res = json.loads(line)
            if not res.get("ok"):
                raise SignerError("Node 生成 %s 失败: %s" % (cmd, res.get("error")))
            return res

    # ---------------------------------------------------------------- 能力
    def dtrait_payload(self, refresh: bool = False) -> dict:
        """设备指纹 payload（进程内缓存 + 磁盘缓存）。

        页面里 dtrait 在**会话内是复用的**（get_qrcode 与 send_code 用的是同一个），
        payload 是设备指纹（稳定）；每次请求变的只是 RSA/AES 加密部分（Python 侧做）。
        所以：进程内缓存 -> 磁盘缓存（TTL 默认 24h）-> 才真去启 nv8 生成。
        """
        if self._dtrait is not None and not refresh:
            return self._dtrait
        if not refresh:
            cached = _read_dtrait_cache()
            if cached is not None:
                self._dtrait = cached
                return cached
        payload = self._call("dtrait")["payload"]
        self._dtrait = payload
        _write_dtrait_cache(payload)
        return payload

    def a_bogus(self, query: str = "", url: str | None = None,
                user_agent: str | None = None, uifid: str | None = None,
                method: str = "GET", body: str | None = None) -> str:
        """生成 a_bogus。

        由 nv8 里的 **bdms** 完成（bdms 是 a_bogus 的真正生成者，见 analysis）。
        建议直接传 `url`（完整 URL，含 query）——bdms 是按路径规则命中的，
        传完整 URL 最贴近真实请求；只给 query 时会拼到 send_code 端点上。

        返回的是 **URL 编码后的**取值（与浏览器实际发出的形式一致）。
        """
        env: dict = {}
        if user_agent:
            env["userAgent"] = user_agent
        if uifid:
            env["uifid"] = uifid
        if url:
            return self._call("abogus", url=url, env=env,
                              method=method, body=body)["a_bogus"]
        return self._call("abogus", query=query, env=env,
                          method=method, body=body)["a_bogus"]


_default: NodeSigner | None = None
_default_lock = threading.Lock()


def default_signer() -> NodeSigner:
    global _default
    with _default_lock:
        if _default is None:
            _default = NodeSigner()
        return _default


# ====================================================================== 异步版
class AsyncNodeSigner:
    """`NodeSigner` 的 asyncio 版本（同一个 Node 常驻服务、同一套 JSON-Lines 协议）。

    用 `asyncio.create_subprocess_exec` + `asyncio.Lock`，全链路线程/协程友好。
    """

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._seq = 0
        self._dtrait: dict | None = None

    async def _start(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        proc = await asyncio.create_subprocess_exec(
            str(_node_path()), str(SERVER_JS),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
        )
        ready = await proc.stdout.readline()
        if b"ready" not in (ready or b""):
            raise SignerError("Node 参数服务启动失败: %r" % ready)
        self._proc = proc
        return proc

    async def close(self) -> None:
        """幂等：可被调用多次（_finish 与 _amain 的 finally 都会调）。"""
        if self._proc is None:
            return
        async with self._lock:
            proc = self._proc
            self._proc = None
            if proc and proc.returncode is None:
                try:
                    proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    async def _call(self, cmd: str, **payload: Any) -> dict:
        async with self._lock:
            proc = await self._start()
            self._seq += 1
            req = {"id": self._seq, "cmd": cmd}
            req.update(payload)
            proc.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            await proc.stdin.drain()
            line = await proc.stdout.readline()
            if not line:
                raise SignerError("Node 参数服务无响应（cmd=%s）" % cmd)
            res = json.loads(line.decode("utf-8"))
            if not res.get("ok"):
                raise SignerError("Node 生成 %s 失败: %s" % (cmd, res.get("error")))
            return res

    async def dtrait_payload(self, refresh: bool = False) -> dict:
        """设备指纹 payload（进程内缓存 + 磁盘缓存），理由同同步版。"""
        if self._dtrait is not None and not refresh:
            return self._dtrait
        if not refresh:
            cached = _read_dtrait_cache()
            if cached is not None:
                self._dtrait = cached
                return cached
        payload = (await self._call("dtrait"))["payload"]
        self._dtrait = payload
        _write_dtrait_cache(payload)
        return payload

    async def a_bogus(self, query: str = "", url: str | None = None,
                      user_agent: str | None = None, uifid: str | None = None,
                      method: str = "GET", body: str | None = None) -> str:
        """生成 a_bogus（nv8 里的 bdms）。返回 URL 编码后的取值。"""
        env: dict = {}
        if user_agent:
            env["userAgent"] = user_agent
        if uifid:
            env["uifid"] = uifid
        if url:
            res = await self._call("abogus", url=url, env=env, method=method, body=body)
        else:
            res = await self._call("abogus", query=query, env=env, method=method, body=body)
        return res["a_bogus"]

    async def signed_url(self, url: str, method: str = "POST", body: str | None = None,
                         user_agent: str | None = None, uifid: str | None = None) -> str:
        """返回**签名后的完整 URL**（bdms 可能自己补 msToken 等参数）。"""
        env: dict = {}
        if user_agent:
            env["userAgent"] = user_agent
        if uifid:
            env["uifid"] = uifid
        res = await self._call("abogus", url=url, env=env, method=method, body=body)
        return res.get("signedUrl") or (url + ("&" if "?" in url else "?") + "a_bogus=" + res["a_bogus"])
