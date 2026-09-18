"""artifact_service.py —— 常驻「窄工件」服务（浏览器 + nv8 只启一次）。

问题：单次调用要付 浏览器启动+页面加载+SDK就绪（~3s）、以及空冷时 nv8/Node 启动（~4.7s）。
批量/频繁调用时这些开销被反复支付。

做法：把这个进程常驻，浏览器与 Node 参数服务都只初始化一次，
对外用很轻的本地 HTTP 暴露两个能力：

    POST /abogus  {"url":..., "method":"POST", "body":...}  -> {"signed_url": "..."}
    POST /dtrait                                            -> {"payload": {...}}
    GET  /health                                            -> {"ok":true,...}

之后每次调用只需毫秒级。

启动：
    runtime\\venv\\Scripts\\python.exe -m utils.artifact_service --port 8787

调用（另一种入口）：
    python main.py --abogus-source service --service-url http://127.0.0.1:8787

安全：只监听 127.0.0.1。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from aiohttp import web

from utils.browser_abogus import DEFAULT_STATE, AsyncBrowserAbogus
from utils.logger import logger
from utils.signer import AsyncNodeSigner


class ArtifactService:
    def __init__(self, state_file: str | Path | None = None, chrome: str | None = None,
                 pages: int = 4) -> None:
        self.state_file = state_file or DEFAULT_STATE
        self.chrome = chrome
        self.pages = pages
        self.bab: AsyncBrowserAbogus | None = None
        self.signer = AsyncNodeSigner()
        self.started = time.time()
        self.counts = {"abogus": 0, "dtrait": 0}

    async def start(self) -> None:
        self.bab = AsyncBrowserAbogus(state_file=self.state_file, chrome=self.chrome,
                                      pages=self.pages)
        t = time.perf_counter()
        await self.bab.__aenter__()
        logger.info("浏览器工件生成器就绪（%.2fs）", time.perf_counter() - t)

    async def stop(self) -> None:
        if self.bab:
            await self.bab.__aexit__(None, None, None)
        await self.signer.close()

    # ------------------------------------------------------------ handlers
    async def h_health(self, _req: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "uptime": round(time.time() - self.started, 1),
            "counts": self.counts,
        })

    async def h_abogus(self, req: web.Request) -> web.Response:
        body = await req.json()
        url = body.get("url") or ""
        if not url:
            raise web.HTTPBadRequest(text=json.dumps({"error": "url required"}))
        t = time.perf_counter()
        try:
            # 页面闲置后可能已重新导航/重建 SDK，导致 send_code 路径注册丢失——
            # 每次签名前重新断言一次（很便宜），并报告当前页面状态便于诊断。
            page_url = self.bab._page.url if self.bab._page else ""
            await self.bab._register_send_code()
            signed = await self.bab.signed_url(url, body.get("method", "POST"), body.get("body"))
        except Exception as exc:
            raise web.HTTPInternalServerError(text=json.dumps({"error": str(exc)})) from exc
        self.counts["abogus"] += 1
        return web.json_response({
            "signed_url": signed,
            "a_bogus": signed.rsplit("a_bogus=", 1)[1],
            "ms": round((time.perf_counter() - t) * 1000, 1),
            "page_url": page_url,
        })

    async def h_dtrait(self, _req: web.Request) -> web.Response:
        try:
            payload = await self.signer.dtrait_payload()
        except Exception as exc:
            raise web.HTTPInternalServerError(text=json.dumps({"error": str(exc)})) from exc
        self.counts["dtrait"] += 1
        return web.json_response({"payload": payload})

    async def h_cookies(self, _req: web.Request) -> web.Response:
        """返回**生成 a_bogus 的那个浏览器会话**的 cookie。

        关键：a_bogus 是绑在浏览器会话/设备上的，调用方必须用**同一会话**的 cookie
        去发请求；不能另建 aiohttp 会话自己取 cookie。
        """
        try:
            cookies = await self.bab.cookies()
        except Exception as exc:
            raise web.HTTPInternalServerError(text=json.dumps({"error": str(exc)})) from exc
        return web.json_response({"cookies": cookies})


def build_app(svc: ArtifactService) -> web.Application:
    app = web.Application()
    app.router.add_get("/health", svc.h_health)
    app.router.add_get("/cookies", svc.h_cookies)
    app.router.add_post("/abogus", svc.h_abogus)
    app.router.add_post("/dtrait", svc.h_dtrait)
    return app


async def _run(port: int, state_file: str | None, chrome: str | None, pages: int) -> None:
    svc = ArtifactService(state_file=state_file, chrome=chrome, pages=pages)
    await svc.start()
    runner = web.AppRunner(build_app(svc))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    logger.info("工件服务已监听 http://127.0.0.1:%d", port)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await svc.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="常驻窄工件服务（浏览器/Node 只启一次）")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE))
    parser.add_argument("--chrome", default=None)
    parser.add_argument("--pages", type=int, default=4,
                        help="页面池大小（= 并发签名能力；单页只能串行，默认 4）")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.port, args.state_file, args.chrome, args.pages))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
