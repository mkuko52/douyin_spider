"""browser_abogus.py —— 用真实浏览器生成 `a_bogus`（窄工件），Python 独占 HTTP 出口。

为什么需要它
------------
`a_bogus` 由页面上的 **bdms**（字节码 VM）生成。我们已经把环境、资源、初始化、
共享全局都对到逐字节一致，服务端仍拒 nv8 自产的 a_bogus（见
`js_reverse_cache/env/env_zero_diff_final.md`）。而**浏览器 bdms 现场生成**的
a_bogus 由 Python 发出 —— 实测 `message:success`。

所以这条路径是当前**可用**的交付形态，且符合项目规约：

    * 浏览器只做**窄工件生成器**：页面内发一个 XHR，在 `send` 处**拦下**，
      只取 bdms 改写后的 URL（含 a_bogus），**不发任何业务请求**；
    * **Python 独占 final live egress**（真正的发码请求由 Python 发出）。

用法
----
    with BrowserAbogus(state_file=...) as bab:
        cookies = bab.cookies()                       # 新鲜的会话 cookie
        a_bogus = bab.abogus(url, method, body)       # 现场生成的签名
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = PROJECT_ROOT / "js_reverse_cache" / "private" / "browser_env_live2.json"
DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 无头 Chrome 的 UA 里带 "HeadlessChrome"，而 bdms 会检测这个字符串（见
# js_reverse_cache/env/bdms_op29_probe.md 的字符串表），从而把"无头环境"编进 a_bogus。
# 因此这里显式覆盖成正常 Chrome 的 UA，并与 Python 发请求时声明的 UA 保持一致。
NORMAL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
VIEWPORT = {"width": 1280, "height": 720}
SCREEN = {"width": 1280, "height": 720}

# 页面加载后需要等的 SDK 就绪标志（secsdk 的签名入口）
READY_JS = "() => !!(window.use && window.use('webSignUrl'))"

# 在页面脚本之前注入：拦下 send_code 的 XHR，只留 URL；并支持"只抓我这一次"
TRAP = r"""
(function () {
  if (window.__babHooked) return;
  window.__babHooked = true;
  window.__bab = { want: false, captured: null, capturedBody: null };
  var oOpen = XMLHttpRequest.prototype.open;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    try {
      var s = String(u);
      this.__babTarget = (s.indexOf('/passport/web/send_code/') >= 0);
      this.__babUrl = s;
      if (this.__babTarget && s.indexOf('a_bogus') >= 0 && window.__bab.want) {
        window.__bab.captured = s;
      }
    } catch (e) {}
    return oOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (b) {
    try {
      if (this.__babTarget && this.__babUrl && this.__babUrl.indexOf('a_bogus') >= 0) {
        if (window.__bab.want) {
          window.__bab.captured = this.__babUrl;
          window.__bab.capturedBody = b ? String(b) : null;
        }
        return;                       // 一律拦下，绝不真发
      }
    } catch (e) {}
    return oSend.apply(this, arguments);
  };
})();
"""


class BrowserAbogusError(RuntimeError):
    pass


class BrowserAbogus:
    """真实浏览器里的 `a_bogus` 工件生成器（上下文管理器）。"""

    def __init__(self, state_file: str | Path | None = None,
                 chrome: str | None = None, ready_timeout: int = 60,
                 headless: bool = True) -> None:
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE
        self.chrome = chrome or DEFAULT_CHROME
        self.ready_timeout = ready_timeout
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    # ---------------------------------------------------------------- 生命周期
    def __enter__(self) -> "BrowserAbogus":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise BrowserAbogusError(
                "需要 playwright：runtime\\venv\\Scripts\\python.exe -m pip install playwright"
            ) from exc

        self._pw = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                # 无头页面闲置会被后台节流，导致唤醒后签名偶发数秒延迟 —— 关掉
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateNativeWinOcclusion",
            ],
        }
        if Path(self.chrome).exists():
            launch_kwargs["executable_path"] = self.chrome
        self._browser = self._pw.chromium.launch(**launch_kwargs)

        ctx_kwargs: dict[str, Any] = {
            "user_agent": NORMAL_UA,
            "viewport": VIEWPORT,
            "screen": SCREEN,
            "device_scale_factor": 1,
        }
        if self.state_file.exists():
            ctx_kwargs["storage_state"] = str(self.state_file)
        self._ctx = self._browser.new_context(**ctx_kwargs)
        self._page = self._ctx.new_page()
        self._page.add_init_script(TRAP)
        _goto_robust_sync(self._page)
        self._wait_ready()
        self._register_send_code()
        return self

    def __exit__(self, *exc: object) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._ctx = self._page = None

    # ---------------------------------------------------------------- 内部
    def _wait_ready(self) -> None:
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            try:
                if self._page.evaluate(READY_JS):
                    return
            except Exception:
                pass
            time.sleep(0.15)
        raise BrowserAbogusError("页面 SDK 未就绪（%ds）：secsdk 的 webSignUrl 未出现" % self.ready_timeout)

    def _register_send_code(self) -> None:
        """页面里 passport SDK 会用 _SdkGlueInit 把 send_code 路径注册给 bdms；
        不补这一步 bdms 不会签我们的请求。"""
        try:
            self._page.evaluate(
                """() => {
                    try {
                        if (typeof window._SdkGlueInit === 'function') {
                            window._SdkGlueInit({ bdms: { paths: ['/passport/web/send_code/'] } },
                                                { bdms: { srcList: [] } });
                            return 'ok';
                        }
                        return 'no _SdkGlueInit';
                    } catch (e) { return 'ERR ' + (e && e.message || e); }
                }"""
            )
        except Exception as exc:
            raise BrowserAbogusError("注册 send_code 路径失败: %s" % exc) from exc

    # ---------------------------------------------------------------- 对外能力
    def cookies(self) -> dict[str, str]:
        """取当前会话 cookie（**只保留抖音域**）。"""
        jar: dict[str, str] = {}
        for cookie in self._ctx.cookies():
            domain = cookie.get("domain") or ""
            if "douyin" not in domain and not domain.endswith("bytedance.com"):
                continue
            if cookie.get("name"):
                jar[cookie["name"]] = cookie.get("value", "")
        return jar

    def signed_url(self, url: str, method: str = "POST", body: str | None = None) -> str:
        """让页面上的 bdms 签名并返回**完整的签名后 URL**。

        注意：bdms 可能自己补参数（实测会补 `msToken`），所以必须用返回的整条 URL 去发，
        而不能只把 a_bogus 拼回原 URL —— 否则签名与实际发出的 query 不一致。
        请求在 `send` 处被拦下，**不会真的发出**。
        """
        page = self._page
        page.evaluate(
            """(spec) => {
                window.__bab.want = true;
                window.__bab.captured = null;
                var x = new XMLHttpRequest();
                x.open(spec.method || 'POST', spec.url);
                x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                x.send(spec.body || null);
            }""",
            {"url": url, "method": method, "body": body or ""},
        )
        captured = None
        for _ in range(20):
            captured = page.evaluate("() => window.__bab.captured")
            if captured:
                break
            time.sleep(0.25)
        page.evaluate("() => { window.__bab.want = false; }")
        if not captured or "a_bogus=" not in captured:
            raise BrowserAbogusError("bdms 未为该 URL 生成 a_bogus")
        return captured

    def abogus(self, url: str, method: str = "POST", body: str | None = None) -> str:
        """只要 a_bogus 取值（兼容旧调用）。"""
        return self.signed_url(url, method, body).rsplit("a_bogus=", 1)[1]



# --------------------------------------------------------------- 导航加固
# 抖音首页有时会以「下载」形式返回（WAF 中间页），Playwright 会直接抛
# "Download is starting"，导致 goto 失败。这里吞掉该错误并重试，后续靠
# 轮询 SDK 是否就绪来判定页面是否真的可用。
def _goto_robust_sync(page, url: str = "https://www.douyin.com/", attempts: int = 3) -> None:
    for i in range(attempts):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as exc:
            msg = str(exc)
            if "Download is starting" in msg or "Navigation" in msg or "Timeout" in msg:
                try:
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                continue
            raise
    # 最后一次不再要求 wait_until，只要提交即可
    try:
        page.goto(url, wait_until="commit", timeout=30000)
    except Exception:
        pass


async def _goto_robust_async(page, url: str = "https://www.douyin.com/", attempts: int = 3) -> None:
    import asyncio as _aio
    for i in range(attempts):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as exc:
            msg = str(exc)
            if "Download is starting" in msg or "Navigation" in msg or "Timeout" in msg:
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                continue
            raise
    try:
        await page.goto(url, wait_until="commit", timeout=30000)
    except Exception:
        pass

def _selftest() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="用真实浏览器生成一次 a_bogus（自检）")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE))
    parser.add_argument("--url",
                        default="https://login.douyin.com/passport/web/send_code/"
                                "?aid=6383&device_platform=web_app")
    parser.add_argument("--body",
                        default="is6Digits=1&mix_mode=1&mobile=2e3d&type=3731&fixed_mix_mode=1")
    args = parser.parse_args()

    with BrowserAbogus(state_file=args.state_file) as bab:
        jar = bab.cookies()
        value = bab.abogus(args.url, method="POST", body=args.body)
    print("cookie 数:", len(jar))
    print("a_bogus :", value[:80], "… len=", len(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())


# ====================================================================== 异步版
class AsyncBrowserAbogus:
    """`BrowserAbogus` 的 asyncio 版本（`async_playwright`）。接口与用法一致：

        async with AsyncBrowserAbogus(state_file=...) as bab:
            cookies = await bab.cookies()
            url = await bab.signed_url(url, "POST", body)
    """

    def __init__(self, state_file: str | Path | None = None,
                 chrome: str | None = None, ready_timeout: int = 60,
                 headless: bool = True,
                 pages: int = 4) -> None:
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE
        self.chrome = chrome or DEFAULT_CHROME
        self.ready_timeout = ready_timeout
        self.headless = headless
        self.pages = max(1, int(pages))
        self._page_pool: list[Any] = []
        self._pool_locks: list[Any] = []
        self._pool_next = 0
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    async def __aenter__(self) -> "AsyncBrowserAbogus":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise BrowserAbogusError(
                r"需要 playwright：runtime\venv\Scripts\python.exe -m pip install playwright"
            ) from exc

        self._pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                # 无头页面闲置会被后台节流，导致唤醒后签名偶发数秒延迟 —— 关掉
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateNativeWinOcclusion",
            ],
        }
        if Path(self.chrome).exists():
            launch_kwargs["executable_path"] = self.chrome
        self._browser = await self._pw.chromium.launch(**launch_kwargs)

        ctx_kwargs: dict[str, Any] = {
            "user_agent": NORMAL_UA,
            "viewport": VIEWPORT,
            "screen": SCREEN,
            "device_scale_factor": 1,
        }
        if self.state_file.exists():
            ctx_kwargs["storage_state"] = str(self.state_file)
        self._ctx = await self._browser.new_context(**ctx_kwargs)
        # 关键：**只先建 1 页**让服务尽快可用（~2.5s）。
        # 一次建 N 页并不行：并发导航 douyin.com 会相互争抢（WAF 限速），
        # 实测 pages=2 启动就要 9~12s。其余页面在后台**逐个**补齐（_grow_pool）。
        import asyncio as _aio

        first = await self._add_page()
        self._page_pool.append(first)
        self._pool_locks.append(_aio.Lock())
        self._page = first
        return self

    async def _add_page(self):
        """新建一页并把它弄到可签状态（SDK 就绪 + 注册 send_code 路径）。"""
        pg = await self._ctx.new_page()
        await pg.add_init_script(TRAP)
        await _goto_robust_async(pg)
        await self._wait_ready(pg)
        await self._register_send_code(pg)
        return pg


    async def __aexit__(self, *exc: object) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._ctx = self._page = None

    async def _wait_ready(self, page=None) -> None:
        import asyncio as _aio
        page = page or self._page
        deadline = _aio.get_event_loop().time() + self.ready_timeout
        while _aio.get_event_loop().time() < deadline:
            try:
                if await page.evaluate(READY_JS):
                    return
            except Exception:
                pass
            await _aio.sleep(0.15)
        raise BrowserAbogusError("页面 SDK 未就绪（%ds）：secsdk 的 webSignUrl 未出现" % self.ready_timeout)

    async def _register_send_code(self, page=None) -> None:
        try:
            await (page or self._page).evaluate(
                """() => {
                    try {
                        if (typeof window._SdkGlueInit === 'function') {
                            window._SdkGlueInit({ bdms: { paths: ['/passport/web/send_code/'] } },
                                                { bdms: { srcList: [] } });
                            return 'ok';
                        }
                        return 'no _SdkGlueInit';
                    } catch (e) { return 'ERR ' + (e && e.message || e); }
                }"""
            )
        except Exception as exc:
            raise BrowserAbogusError("注册 send_code 路径失败: %s" % exc) from exc

    async def cookies(self) -> dict[str, str]:
        jar: dict[str, str] = {}
        for cookie in await self._ctx.cookies():
            domain = cookie.get("domain") or ""
            if "douyin" not in domain and not domain.endswith("bytedance.com"):
                continue
            if cookie.get("name"):
                jar[cookie["name"]] = cookie.get("value", "")
        return jar

    async def signed_url(self, url: str, method: str = "POST", body: str | None = None) -> str:
        """返回**完整的签名后 URL**（bdms 可能自补 msToken 等）；请求在 send 处被拦下。

        并发安全：从页面池轮询取一个页面并持有它的锁，
        避免并发请求互相覆盖页面里的 `window.__bab` 交接状态。
        """
        if not self._page_pool:
            return await self._signed_url_on(self._page, url, method, body)
        n = len(self._page_pool)
        # 优先取空闲页（不阻塞、不抢别人）
        for k in range(n):
            idx = (self._pool_next + k) % n
            if not self._pool_locks[idx].locked():
                self._pool_next = idx + 1
                async with self._pool_locks[idx]:
                    return await self._signed_url_on(self._page_pool[idx], url, method, body)
        # 全忙：能扩就惰性扩一页（只在真有并发时付建页成本，空闲时不打扰）
        if n < self.pages:
            import asyncio as _aio2
            pg = await self._add_page()
            lock = _aio2.Lock()
            self._page_pool.append(pg)
            self._pool_locks.append(lock)
            async with lock:
                return await self._signed_url_on(pg, url, method, body)
        # 已到上限：排队等第一个
        idx = self._pool_next % n
        self._pool_next += 1
        async with self._pool_locks[idx]:
            return await self._signed_url_on(self._page_pool[idx], url, method, body)

    async def _signed_url_on(self, page, url: str, method: str, body: str | None) -> str:
        import asyncio as _aio
        await page.evaluate(
            """(spec) => {
                window.__bab.want = true;
                window.__bab.captured = null;
                var x = new XMLHttpRequest();
                x.open(spec.method || 'POST', spec.url);
                x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                x.send(spec.body || null);
            }""",
            {"url": url, "method": method, "body": body or ""},
        )
        captured = None
        for _ in range(30):
            captured = await page.evaluate("() => window.__bab.captured")
            if captured:
                break
            await _aio.sleep(0.1)
        await page.evaluate("() => { window.__bab.want = false; }")
        if not captured or "a_bogus=" not in captured:
            raise BrowserAbogusError("bdms 未为该 URL 生成 a_bogus")
        return captured

    async def abogus(self, url: str, method: str = "POST", body: str | None = None) -> str:
        return (await self.signed_url(url, method, body)).rsplit("a_bogus=", 1)[1]