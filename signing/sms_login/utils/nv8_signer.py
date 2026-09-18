"""nv8_signer.py —— Python → Node(**nv8**) 桥：用真实 bdms 字节码生成 `a_bogus`（全异步）。

与 `signer.py`（pyexecjs2 + `node/mod.js` 公开移植版）的区别：
- `mod.js` 是**公开复现的算法**，服务端实测不认（有效码请求被判 `7`）；
- 本模块跑的是**页面同款 bdms 字节码**（`js_reverse_cache/source/bdms.js`），
  由 nv8 补出浏览器环境后执行，输出与浏览器同结构（188 字符）。

边界：Node 侧**不发任何网络**（XHR 全部走本地桩）；HTTP 出口属于 Python。

用法（异步）：
    from utils.nv8_signer import default_signer
    signer = default_signer()
    r = await signer.abogus(url, "POST", body)     # -> {"a_bogus": ..., "signedUrl": ...}
    await signer.close()
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_JS = ROOT / "node" / "abogus_server.mjs"
LOCAL_NODE = ROOT.parent / "send_code" / "runtime" / "node_local" / "node.exe"
NV8_SRC = os.environ.get("NV8_SRC", "D:/develop_software/nv8/src/index.js")


class Nv8Error(RuntimeError):
    pass


def _node() -> str:
    override = os.environ.get("NV8_NODE")
    if override:
        return override
    if LOCAL_NODE.exists():
        return str(LOCAL_NODE)
    found = shutil.which("node")
    if not found:
        raise Nv8Error("找不到 node（可用 NV8_NODE 指定）")
    return found


class AsyncNv8Signer:
    """常驻 Node 子进程（JSON-Lines over stdio），全异步、用锁串行化。

    nv8 沙箱冷启动约 5s，所以务必复用同一个进程（`default_signer()`），不要每次新起。
    """

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._seq = 0

    async def _start(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        if not SERVER_JS.exists():
            raise Nv8Error("缺 %s" % SERVER_JS)
        if not Path(NV8_SRC).exists():
            raise Nv8Error("找不到 nv8：%s（用 NV8_SRC 覆盖）" % NV8_SRC)
        proc = await asyncio.create_subprocess_exec(
            _node(), str(SERVER_JS),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, cwd=str(ROOT),
            env={**os.environ, "NV8_SRC": NV8_SRC},
        )
        ready = await proc.stdout.readline()
        if b"ready" not in (ready or b""):
            raise Nv8Error("nv8 签名服务启动失败: %r" % ready)
        self._proc = proc
        return proc

    async def close(self) -> None:
        """幂等：可被多次调用。"""
        if self._proc is None:
            return
        async with self._lock:
            proc, self._proc = self._proc, None
            if proc and proc.returncode is None:
                try:
                    proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    async def abogus(self, url: str, method: str = "POST", body: str | None = None) -> dict:
        """返回 `{"a_bogus": ..., "signedUrl": ...}`；请求在页面桩里被拦下，不真发。"""
        async with self._lock:
            proc = await self._start()
            self._seq += 1
            proc.stdin.write((json.dumps({"id": self._seq, "cmd": "abogus", "url": url,
                                          "method": method, "body": body}) + "\n").encode())
            await proc.stdin.drain()
            line = await proc.stdout.readline()
            if not line:
                raise Nv8Error("nv8 签名服务无响应")
            res = json.loads(line.decode("utf-8"))
            if not res.get("ok"):
                raise Nv8Error("nv8 生成 a_bogus 失败: %s" % res.get("error"))
            return res


_default: AsyncNv8Signer | None = None


def default_signer() -> AsyncNv8Signer:
    global _default
    if _default is None:
        _default = AsyncNv8Signer()
    return _default


if __name__ == "__main__":   # 自检（纯离线，不发网络）
    async def _main() -> None:
        s = default_signer()
        try:
            r = await s.abogus("https://login.douyin.com/passport/web/sms_login/?aid=6383&sign=aa&qs=bb",
                               "POST", "mix_mode=1")
            print("a_bogus len:", len(r["a_bogus"]))
            print("signedUrl  :", r["signedUrl"][:110])
        finally:
            await s.close()

    asyncio.run(_main())
