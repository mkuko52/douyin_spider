"""dtrait_signer.py —— Python → Node(nv8) 桥：采集 `x-tt-session-dtrait` 的 payload（全异步）。

边界（Non-Negotiables）：
- Node 侧**只采集设备指纹**，不发任何网络（见 `node/dtrait_server.mjs`）。
- RSA/AES 加密与最终 HTTP 出口都在 Python。

nv8 是「补环境框架」：`uc-secure-dtrait-core` 是 JSVMP 库，会读 navigator/screen/
canvas/WebGL 等浏览器特征，裸 Node 跑不了，nv8 负责把这些补成“检测不出来”。

payload 是**设备级、稳定的**；每次请求变的只是 RSA/AES 那层（由 Python 现场算）。
所以这里做进程内 + 磁盘缓存（TTL 默认 24h，可用 `DTRAIT_TTL` 覆盖）。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_JS = ROOT / "node" / "dtrait_server.mjs"
LOCAL_NODE = ROOT.parent / "send_code" / "runtime" / "node_local" / "node.exe"
CACHE = ROOT / "js_reverse_cache" / "private" / "dtrait_payload_cache.json"
TTL = float(os.environ.get("DTRAIT_TTL", "86400"))


class DtraitError(RuntimeError):
    pass


def _node() -> str:
    override = os.environ.get("NV8_NODE")
    if override:
        return override
    if LOCAL_NODE.exists():
        return str(LOCAL_NODE)
    found = shutil.which("node")
    if not found:
        raise DtraitError("找不到 node（可用 NV8_NODE 指定）")
    return found


def _read_cache() -> dict | None:
    try:
        if CACHE.exists() and (time.time() - CACHE.stat().st_mtime) <= TTL:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("str"):
                return data
    except Exception:
        pass
    return None


def _write_cache(payload: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


class AsyncDtraitSigner:
    """常驻 Node 子进程（JSON-Lines over stdio），全异步、用锁串行化。"""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._seq = 0

    async def _start(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        if not SERVER_JS.exists():
            raise DtraitError("缺 %s" % SERVER_JS)
        proc = await asyncio.create_subprocess_exec(
            _node(), str(SERVER_JS),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, cwd=str(ROOT),
        )
        ready = await proc.stdout.readline()
        if b"ready" not in (ready or b""):
            raise DtraitError("nv8 dtrait 服务启动失败: %r" % ready)
        self._proc = proc
        return proc

    async def close(self) -> None:
        """幂等。"""
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

    async def payload(self, refresh: bool = False) -> dict:
        if not refresh:
            cached = _read_cache()
            if cached is not None:
                return cached
        async with self._lock:
            proc = await self._start()
            self._seq += 1
            proc.stdin.write((json.dumps({"id": self._seq, "cmd": "dtrait"}) + "\n").encode())
            await proc.stdin.drain()
            line = await proc.stdout.readline()
            if not line:
                raise DtraitError("nv8 dtrait 服务无响应")
            res = json.loads(line.decode("utf-8"))
            if not res.get("ok"):
                raise DtraitError("采集失败: %s" % res.get("error"))
        payload = res["payload"]
        _write_cache(payload)
        return payload


_default: AsyncDtraitSigner | None = None


def default_signer() -> AsyncDtraitSigner:
    global _default
    if _default is None:
        _default = AsyncDtraitSigner()
    return _default


if __name__ == "__main__":   # 自检
    async def _main() -> None:
        from utils import dtrait as dtrait_mod
        s = default_signer()
        try:
            p = await s.payload()
            strings = p.get("str", {})
            print("payload: str=%d 非零=%d bool=%d" % (
                len(strings), sum(1 for v in strings.values() if v not in (0, "0")),
                len(p.get("bool", {}))))
            version, wrap, body = dtrait_mod.build(p).split("_")
            print("dtrait 段长:", [len(version), len(wrap), len(body)])
        finally:
            await s.close()

    asyncio.run(_main())
