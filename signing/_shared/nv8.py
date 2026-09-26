"""nv8.py —— 数据接口的本地 bdms a_bogus / secsdk webSignUrl。

为什么要真 bdms：`/aweme/v1/web/comment/list/reply/` **不认**公开 `mod.js` 的 a_bogus ——
同一份 query，只有 a_bogus 不同：mod.js → `text/plain` 空 body ❌；真 bdms → `status_code=0` ✅。
（详情还需 secsdk webSignUrl；回复需真 bdms。）

**两种取法**：

| 取法 | 代价 | 说明 |
|---|---|---|
| 常驻服务（推荐） | ~50ms | `python -m _shared.nv8_service`（或 `start_nv8_service.bat`），Node **只启一次** |
| 本进程起 Node（回落） | ~5s | 服务没开时自动回落，保证单独跑 CLI 也能用 |

服务地址：`NV8_SERVICE_URL`（默认 `http://127.0.0.1:8789`）。

**不复制工件**：Node 侧跑的是 `sms_login/node/abogus_server.mjs`（它自带 bdms 字节码 / assets /
环境画像，`ROOT` 按自身路径解析）。登录项目是 bdms 工件的唯一持有者。

边界：Node 侧只生成参数，**不发网络**；Python（`requests`）独占 HTTP 出口。
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .node import node_path

ROOT = Path(__file__).resolve().parent                      # signing/_shared
SERVER_JS = ROOT.parent / "sms_login" / "node" / "abogus_server.mjs"
NV8_SRC = os.environ.get("NV8_SRC", "D:/develop_software/nv8/src/index.js")
SERVICE_URL = os.environ.get("NV8_SERVICE_URL", "http://127.0.0.1:8789").rstrip("/")


class Nv8Error(RuntimeError):
    pass


def _node() -> str:
    found = node_path()
    if not found:
        raise Nv8Error("找不到 node（可用 DOUYIN_NODE 指定，或装到 PATH）")
    return found


_proc: subprocess.Popen | None = None
_lock = threading.Lock()
_seq = 0


def is_warm() -> bool:
    return bool(_proc and _proc.poll() is None)


def _start() -> subprocess.Popen:
    """起常驻 Node（JSON-Lines over stdio）。nv8 冷启动 ~5s，所以进程内复用。"""
    global _proc
    if is_warm():
        return _proc  # type: ignore[return-value]
    if not SERVER_JS.exists():
        raise Nv8Error("缺 %s" % SERVER_JS)
    if not Path(NV8_SRC).exists():
        raise Nv8Error("找不到 nv8：%s（用 NV8_SRC 覆盖）" % NV8_SRC)
    proc = subprocess.Popen(
        [_node(), str(SERVER_JS)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=str(SERVER_JS.parent.parent), text=True, encoding="utf-8", bufsize=1,
        env={**os.environ, "NV8_SRC": NV8_SRC},
    )
    ready = proc.stdout.readline()
    if "ready" not in (ready or ""):
        raise Nv8Error("nv8 签名服务启动失败: %r" % ready)
    _proc = proc
    return proc


def warmup() -> None:
    """起 Node 并让它把 VM 热起来（第一次生成通常比后续慢）。"""
    a_bogus_local("https://www.douyin.com/aweme/v1/web/tab/feed/?count=1")


def a_bogus_local(url: str, method: str = "GET", body: str | None = None) -> str:
    """在**本进程**起/复用 Node 生成 a_bogus（未 URL 编码）。"""
    global _seq
    with _lock:
        proc = _start()
        _seq += 1
        proc.stdin.write(json.dumps({"id": _seq, "cmd": "abogus", "url": url,
                                     "method": method, "body": body}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise Nv8Error("nv8 签名服务无响应")
        res = json.loads(line)
        if not res.get("ok"):
            raise Nv8Error("nv8 生成 a_bogus 失败: %s" % res.get("error"))
        return res["a_bogus"]


def web_sign(url: str, uifid: str) -> tuple[str, dict]:
    """本地 secsdk webSignUrl：只生成 URL 和附加请求头，不发 HTTP 请求。"""
    global _seq
    with _lock:
        proc = _start()
        _seq += 1
        proc.stdin.write(json.dumps({"id": _seq, "cmd": "websign", "url": url,
                                     "uifid": uifid}) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise Nv8Error("nv8 webSignUrl 无响应")
        res = json.loads(line)
        if not res.get("ok") or not isinstance(res.get("result"), dict):
            raise Nv8Error("nv8 webSignUrl 失败: %s" % res.get("error"))
        signed = res["result"]
        if not signed.get("url") or not isinstance(signed.get("headers"), dict):
            raise Nv8Error("nv8 webSignUrl 未返回 URL/请求头")
        return signed["url"], signed["headers"]


def _from_service(url: str, method: str, body: str | None, timeout: float = 60.0) -> str:
    payload = json.dumps({"url": url, "method": method, "body": body}).encode()
    req = urllib.request.Request(SERVICE_URL + "/abogus", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if not res.get("ok"):
        raise Nv8Error(res.get("error") or "常驻服务返回失败")
    return res["a_bogus"]


def a_bogus(url: str, method: str = "GET", body: str | None = None) -> str:
    """优先走常驻服务（~50ms），服务没开则回落本进程起 Node（~5s）。"""
    try:
        return _from_service(url, method, body)
    except (urllib.error.URLError, OSError, ValueError, KeyError, Nv8Error):
        return a_bogus_local(url, method, body)


def close() -> None:
    global _proc
    proc, _proc = _proc, None
    if proc and proc.poll() is None:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:                                   # noqa: BLE001
            try:
                proc.kill()
            except Exception:                               # noqa: BLE001
                pass


atexit.register(close)
