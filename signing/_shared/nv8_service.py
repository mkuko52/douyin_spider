"""nv8_service.py —— 常驻 nv8 工件服务（HTTP）：Node/bdms 只启一次。

为什么要它：`nv8.py` 每次起 Node 冷启动约 5s；本服务把 Node 进程常驻，
`replies` 之类的调用从 ~5s 降到 ~50ms。

跑法：
    python -m _shared.nv8_service                 # 默认 127.0.0.1:8789
    signing/_shared/start_nv8_service.bat         # Windows
    signing/_shared/start_nv8_service.sh          # Linux/macOS

接口：
    GET  /health   -> {"ok": true, "warm": true}
    POST /abogus   {"url": "...", "method": "GET", "body": null}
                   -> {"ok": true, "a_bogus": "..."}

调用方：`_shared/nv8.py` 的 `a_bogus()` 会优先打这个服务（`NV8_SERVICE_URL` 可覆盖），
服务没开时自动回落本进程起 Node。**本文件是 `_shared/nv8.py` 之上的薄壳**，不含签名逻辑。
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # signing/

from _shared import nv8                                        # noqa: E402

DEFAULT_PORT = 8789


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):                         # 静音（stdout 留给启动信息）
        pass

    def _json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                          # noqa: N802
        if self.path.split("?")[0] == "/health":
            self._json({"ok": True, "warm": nv8.is_warm()})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):                                         # noqa: N802
        if self.path.split("?")[0] != "/abogus":
            self._json({"ok": False, "error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("content-length") or 0)
            req = json.loads(self.rfile.read(length) or b"{}")
            value = nv8.a_bogus_local(req["url"], req.get("method", "GET"), req.get("body"))
            self._json({"ok": True, "a_bogus": value})
        except Exception as exc:                               # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="常驻 nv8 a_bogus 工件服务（Node 只启一次）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-warm", action="store_true", help="启动时不预热（第一次调用会慢）")
    args = parser.parse_args()

    print(f"[nv8-service] 预热 nv8（冷启动约 5s）…", flush=True)
    if not args.no_warm:
        try:
            nv8.warmup()
        except Exception as exc:                                # noqa: BLE001
            print(f"[nv8-service] 预热失败（首次调用会再试）：{exc}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[nv8-service] listening on http://{args.host}:{args.port}  "
          f"(GET /health, POST /abogus)  warm={nv8.is_warm()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        nv8.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
