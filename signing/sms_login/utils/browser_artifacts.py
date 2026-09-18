"""browser_artifacts.py —— 用真实浏览器产出**窄工件**：`a_bogus` + `dtrait` + 会话 cookie。

来源：`send_code` 项目已验证可行的形态（浏览器只做窄工件生成器，Python 独占 HTTP 出口）。
本文件按 `sms_login` 路径适配（`/passport/web/sms_login/`）。

为什么需要它：`a_bogus` 由页面 **bdms**（字节码 VM）生成、`x-tt-session-dtrait`
由 `uc-secure-dtrait-core` 按**该浏览器会话的真实环境**采集。nv8 能补环境，
但补出来的是“另一台设备”的画像；本模块拿的是**同一个会话自己会发的值**。

边界：页面里的 XHR 在 `send` 处**被拦下，不真的发出**；
返回的 URL / headers 交给 Python，由 Python 发出真正的请求。

依赖：playwright（+ 本机 Chrome）。没装就走 `--abogus-source modjs`（纯 Node）。
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "js_reverse_cache" / "private" / "browser_state.json"
DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 无头 Chrome 的 UA 带 "HeadlessChrome"，bdms 会把它编进 a_bogus；覆盖成正常 Chrome，
# 并与 Python 发请求时声明的 UA 一致。
NORMAL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
VIEWPORT = {"width": 1280, "height": 720}
SCREEN = {"width": 1280, "height": 720}

READY_JS = "() => !!(window.use && window.use('webSignUrl'))"

# 注意：init script 先装，bdms 后装 → bdms 成为最外层，改写完 URL 才调到这里，
# 所以我们拿到的是**已经补好 a_bogus** 的 URL。
TRAP = r"""
(function () {
  if (window.__lab) return;
  window.__lab = { want: false, url: null, headers: null, body: null };
  var oOpen = XMLHttpRequest.prototype.open;
  var oSet = XMLHttpRequest.prototype.setRequestHeader;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    try {
      this.__labTarget = String(u).indexOf('/passport/web/sms_login/') >= 0;
      this.__labUrl = String(u);
      this.__labHeaders = {};
    } catch (e) {}
    return oOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    try { if (this.__labTarget) this.__labHeaders[String(k).toLowerCase()] = String(v); } catch (e) {}
    return oSet.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (b) {
    try {
      if (this.__labTarget && this.__labUrl && this.__labUrl.indexOf('a_bogus') >= 0) {
        if (window.__lab.want) {
          window.__lab.url = this.__labUrl;
          window.__lab.headers = this.__labHeaders;
          window.__lab.body = b ? String(b) : null;
        }
        return;                       // 一律拦下，绝不真发
      }
    } catch (e) {}
    return oSend.apply(this, arguments);
  };
})();
"""

# 我们要从浏览器现场拿走的头（其余由 Python 自己生成）
WANTED_HEADERS = ("x-tt-session-dtrait", "x-tt-passport-verify-portrait",
                  "x-tt-passport-trace-id", "x-tt-passport-csrf-token")


class BrowserArtifactError(RuntimeError):
    pass


def available() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


class BrowserArtifacts:
    """同步版（供 recon / 线程调用）。异步交付请用 :class:`AsyncBrowserArtifacts`。"""

    def __init__(self, state_file: str | pathlib.Path | None = None,
                 chrome: str | None = None, headless: bool = True,
                 ready_timeout: int = 60) -> None:
        self.state_file = pathlib.Path(state_file) if state_file else DEFAULT_STATE
        self.chrome = chrome or DEFAULT_CHROME
        self.headless = headless
        self.ready_timeout = ready_timeout
        self._pw = self._browser = self._ctx = self._page = None

    # ------------------------------------------------------------ 生命周期
    def __enter__(self) -> "BrowserArtifacts":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserArtifactError(
                "需要 playwright：pip install playwright") from exc

        self._pw = sync_playwright().start()
        kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled",
                     "--disable-background-timer-throttling",
                     "--disable-backgrounding-occluded-windows",
                     "--disable-renderer-backgrounding"],
        }
        if pathlib.Path(self.chrome).exists():
            kwargs["executable_path"] = self.chrome
        self._browser = self._pw.chromium.launch(**kwargs)

        ctx_kwargs: dict[str, Any] = {"user_agent": NORMAL_UA, "viewport": VIEWPORT,
                                      "screen": SCREEN, "device_scale_factor": 1}
        if self.state_file.exists():
            ctx_kwargs["storage_state"] = str(self.state_file)
        self._ctx = self._browser.new_context(**ctx_kwargs)
        self._page = self._ctx.new_page()
        self._page.add_init_script(TRAP)
        self._goto()
        self._wait_ready()
        self._register()
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
    def _goto(self) -> None:
        for wait in ("domcontentloaded", "commit"):
            for _ in range(3):
                try:
                    self._page.goto("https://www.douyin.com/", wait_until=wait, timeout=60000)
                    # 首页会做 SPA 跳转（→ /jingxuan）；等它稳定，否则 evaluate 会撞上
                    # “Execution context was destroyed”。
                    self._page.wait_for_timeout(4000)
                    return
                except Exception:
                    time.sleep(1.0)
        raise BrowserArtifactError("页面打开失败")

    def _eval(self, script: str, arg=None):
        """evaluate 包装：SPA 跳转期间重试一次。"""
        last = None
        for attempt in range(2):
            try:
                return self._page.evaluate(script, arg) if arg is not None \
                    else self._page.evaluate(script)
            except Exception as exc:            # noqa: BLE001
                last = exc
                self._page.wait_for_timeout(1500)
        raise BrowserArtifactError("页面脚本执行失败: %s" % last)

    def _wait_ready(self) -> None:
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            try:
                if self._eval(READY_JS):
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise BrowserArtifactError("页面 SDK 未就绪")

    def _register(self) -> None:
        self._eval(
            """() => {
                try {
                    if (typeof window._SdkGlueInit === 'function') {
                        window._SdkGlueInit({ bdms: { paths: ['/passport/web/sms_login/'] } },
                                            { bdms: { srcList: [] } });
                        return 'ok';
                    }
                    return 'no _SdkGlueInit';
                } catch (e) { return 'ERR ' + (e && e.message || e); }
            }"""
        )

    # ---------------------------------------------------------------- 对外
    def cookies(self) -> dict[str, str]:
        jar: dict[str, str] = {}
        for cookie in self._ctx.cookies():
            domain = cookie.get("domain") or ""
            if "douyin" not in domain and not domain.endswith("bytedance.com"):
                continue
            if cookie.get("name"):
                jar[cookie["name"]] = cookie.get("value", "")
        return jar

    def sign(self, url: str, method: str = "POST", body: str | None = None) -> dict:
        """让浏览器给这条 URL 生成现场工件。

        返回 `{url, a_bogus, headers, body}`：`url` 是 bdms 改写后的完整 URL
        （可能自补了 msToken），`headers` 只含 `WANTED_HEADERS` 里出现的项。
        请求在 `send` 处被拦下，**不会真的发出**。
        """
        self._eval(
            """(spec) => {
                window.__lab.want = true;
                window.__lab.url = null; window.__lab.headers = null; window.__lab.body = null;
                var x = new XMLHttpRequest();
                x.open(spec.method || 'POST', spec.url);
                x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                x.send(spec.body || null);
            }""",
            {"url": url, "method": method, "body": body or ""},
        )
        deadline = time.time() + 30
        captured = None
        while time.time() < deadline:
            captured = self._eval("() => window.__lab")
            if captured and captured.get("url"):
                break
            time.sleep(0.05)
        self._eval("() => { window.__lab.want = false; }")
        if not captured or not captured.get("url"):
            raise BrowserArtifactError("浏览器没有产出签名 URL（路径未注册或页面未就绪）")

        signed = captured["url"]
        headers = {k: v for k, v in (captured.get("headers") or {}).items()
                   if k in WANTED_HEADERS}
        return {"url": signed,
                "a_bogus": signed.rsplit("a_bogus=", 1)[-1] if "a_bogus=" in signed else None,
                "headers": headers,
                "body": captured.get("body")}


class AsyncBrowserArtifacts:
    """`BrowserArtifacts` 的 asyncio 版（`playwright.async_api`）。

    与 `send_code` 的 `AsyncBrowserAbogus` 同一形态：页面里的 XHR 在 `send` 处被拦下，
    不发业务请求；返回的 URL / headers 交给 Python，由 `aiohttp` 发出真正的请求。
    """

    def __init__(self, state_file: str | pathlib.Path | None = None,
                 chrome: str | None = None, headless: bool = True,
                 ready_timeout: int = 60) -> None:
        self.state_file = pathlib.Path(state_file) if state_file else DEFAULT_STATE
        self.chrome = chrome or DEFAULT_CHROME
        self.headless = headless
        self.ready_timeout = ready_timeout
        self._pw = self._browser = self._ctx = self._page = None

    async def __aenter__(self) -> "AsyncBrowserArtifacts":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserArtifactError("需要 playwright：pip install playwright") from exc

        self._pw = await async_playwright().start()
        kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled",
                     "--disable-background-timer-throttling",
                     "--disable-backgrounding-occluded-windows",
                     "--disable-renderer-backgrounding"],
        }
        if pathlib.Path(self.chrome).exists():
            kwargs["executable_path"] = self.chrome
        self._browser = await self._pw.chromium.launch(**kwargs)

        ctx_kwargs: dict[str, Any] = {"user_agent": NORMAL_UA, "viewport": VIEWPORT,
                                      "screen": SCREEN, "device_scale_factor": 1}
        if self.state_file.exists():
            ctx_kwargs["storage_state"] = str(self.state_file)
        self._ctx = await self._browser.new_context(**ctx_kwargs)
        self._page = await self._ctx.new_page()
        await self._page.add_init_script(TRAP)
        await self._goto()
        await self._wait_ready()
        await self._register()
        return self

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

    async def _eval(self, script: str, arg=None):
        """evaluate 包装：SPA 跳转期间重试一次。"""
        last = None
        for _ in range(2):
            try:
                return await (self._page.evaluate(script, arg) if arg is not None
                              else self._page.evaluate(script))
            except Exception as exc:            # noqa: BLE001
                last = exc
                await self._page.wait_for_timeout(1500)
        raise BrowserArtifactError("页面脚本执行失败: %s" % last)

    async def _goto(self) -> None:
        import asyncio
        for wait in ("domcontentloaded", "commit"):
            for _ in range(3):
                try:
                    await self._page.goto("https://www.douyin.com/", wait_until=wait,
                                          timeout=60000)
                    await self._page.wait_for_timeout(4000)   # 等 SPA 跳转稳定
                    return
                except Exception:
                    await asyncio.sleep(1.0)
        raise BrowserArtifactError("页面打开失败")

    async def _wait_ready(self) -> None:
        import asyncio
        await self._page.wait_for_function(READY_JS, timeout=self.ready_timeout * 1000)

    async def _register(self) -> None:
        await self._eval(
            """() => {
                try {
                    if (typeof window._SdkGlueInit === 'function') {
                        window._SdkGlueInit({ bdms: { paths: ['/passport/web/sms_login/'] } },
                                            { bdms: { srcList: [] } });
                        return 'ok';
                    }
                    return 'no _SdkGlueInit';
                } catch (e) { return 'ERR ' + (e && e.message || e); }
            }"""
        )

    async def cookies(self) -> dict[str, str]:
        jar: dict[str, str] = {}
        for cookie in await self._ctx.cookies():
            domain = cookie.get("domain") or ""
            if "douyin" not in domain and not domain.endswith("bytedance.com"):
                continue
            if cookie.get("name"):
                jar[cookie["name"]] = cookie.get("value", "")
        return jar

    async def sign(self, url: str, method: str = "POST", body: str | None = None) -> dict:
        import asyncio
        await self._eval(
            """(spec) => {
                window.__lab.want = true;
                window.__lab.url = null; window.__lab.headers = null; window.__lab.body = null;
                var x = new XMLHttpRequest();
                x.open(spec.method || 'POST', spec.url);
                x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                x.send(spec.body || null);
            }""",
            {"url": url, "method": method, "body": body or ""},
        )
        deadline = asyncio.get_running_loop().time() + 30
        captured = None
        while asyncio.get_running_loop().time() < deadline:
            captured = await self._eval("() => window.__lab")
            if captured and captured.get("url"):
                break
            await asyncio.sleep(0.05)
        await self._eval("() => { window.__lab.want = false; }")
        if not captured or not captured.get("url"):
            raise BrowserArtifactError("浏览器没有产出签名 URL（路径未注册或页面未就绪）")
        signed = captured["url"]
        return {"url": signed,
                "a_bogus": signed.rsplit("a_bogus=", 1)[-1] if "a_bogus=" in signed else None,
                "headers": {k: v for k, v in (captured.get("headers") or {}).items()
                            if k in WANTED_HEADERS},
                "body": captured.get("body")}
