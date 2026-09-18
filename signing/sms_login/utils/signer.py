"""signer.py —— pyexecjs2 桥：用 Node 生成 `a_bogus`。

边界（Non-Negotiables）：
- Node 侧**只生成参数**，不发任何网络请求（`node/mod.js` 全文无 fetch/XHR）。
- Python 独占最终 HTTP 出口。

pyexecjs2 的导入名是 `execjs`（包名 `pyexecjs2`）。

用法：
    from utils.signer import a_bogus, signed_query
    bogus = a_bogus("a=1&b=2")
    query = signed_query(params)          # 追加 a_bogus 后的完整 query
"""

from __future__ import annotations

import pathlib
import threading
import time

import execjs

ROOT = pathlib.Path(__file__).resolve().parents[1]
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
        _ctx = execjs.compile(MOD_JS.read_text(encoding="utf-8"), cwd=str(MOD_JS.parent))
    return _ctx


def a_bogus(query: str, options: dict | None = None) -> str:
    """对 query 串生成 a_bogus（Node/mod.js）。返回**未 URL 编码**的原始取值。"""
    with _lock:
        ctx = _context()
        t0 = time.time()
        try:
            value = ctx.call("signABogus", query, options or {})
        except Exception as exc:               # pragma: no cover - 运行环境缺失
            raise SignerError("生成 a_bogus 失败：%s" % exc) from exc
        _stats["calls"] += 1
        _stats["ms"] += (time.time() - t0) * 1000
    if not value:
        raise SignerError("a_bogus 为空")
    return value


def stats() -> dict:
    return {"calls": _stats["calls"],
            "avg_ms": round(_stats["ms"] / _stats["calls"], 1) if _stats["calls"] else 0.0}


if __name__ == "__main__":   # 自检（freeze 固定 Date/Math.random 后应逐位可复现）
    frozen = {"freeze": {"now": 1789740278617, "seed": 42}}
    v1 = a_bogus("a=1&b=2", frozen)
    v2 = a_bogus("a=1&b=2", frozen)
    print("a_bogus:", len(v1), v1[:48])
    assert len(v1) > 100 and v1 == v2, "同输入 + 同 freeze 应逐位可复现"
    assert a_bogus("a=1&b=2") != v1, "不同 freeze 应产生不同取值"
    print("稳定可复现 ✓  ", stats())
