"""signer.py —— pyexecjs2 桥：用 Node 生成 `a_bogus`（数据接口共用，唯一一份）。

边界（Non-Negotiables）：
- Node 侧**只生成参数**，不发任何网络请求（`node/mod.js` 全文无 fetch/XHR）。
- Python（`requests`）独占最终 HTTP 出口。

`node/mod.js` 与旧项目 `douyin_spider/mod.js`、`send_code/node/mod.js`、
`sms_login/node/mod.js` 字节一致，且已 live 验证：
数据接口（`/aweme/v1/web/*`）**只需 a_bogus，不需要浏览器 / dtrait**。

pyexecjs2 的导入名是 `execjs`（包名 `pyexecjs2`）。
"""

from __future__ import annotations

import pathlib
import threading
import time

import execjs

from .node import ensure_on_path

ROOT = pathlib.Path(__file__).resolve().parent
MOD_JS = ROOT / "node" / "mod.js"

_ctx: execjs.Context | None = None
_lock = threading.Lock()
_stats = {"calls": 0, "ms": 0.0}


class SignerError(RuntimeError):
    pass


def _context() -> execjs.Context:
    global _ctx
    if _ctx is None:
        if not MOD_JS.exists():
            raise SignerError("缺 node/mod.js：%s" % MOD_JS)
        # execjs 靠 PATH 找 node → 先把项目自带 node 插到最前（不依赖系统 PATH）
        ensure_on_path()
        _ctx = execjs.compile(MOD_JS.read_text(encoding="utf-8"), cwd=str(MOD_JS.parent))
    return _ctx


def sign_url(url: str, options: dict | None = None) -> str:
    """返回带 `a_bogus` 的完整 URL（mod.js 的 `signUrl`）。"""
    with _lock:
        ctx = _context()
        t0 = time.time()
        try:
            value = ctx.call("signUrl", str(url), options or {})
        except Exception as exc:               # pragma: no cover - 运行环境缺失
            raise SignerError("生成 a_bogus 失败：%s" % exc) from exc
        _stats["calls"] += 1
        _stats["ms"] += (time.time() - t0) * 1000
    if not value or "a_bogus=" not in value:
        raise SignerError("a_bogus 为空")
    return value


def a_bogus(query: str, options: dict | None = None) -> str:
    """只算 a_bogus（离线固定向量用），返回**未 URL 编码**的原始取值。"""
    with _lock:
        ctx = _context()
        value = ctx.call("signABogus", str(query), options or {})
    if not value:
        raise SignerError("a_bogus 为空")
    return value


def stats() -> dict:
    return dict(_stats)
