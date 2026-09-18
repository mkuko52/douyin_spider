r"""main.py —— 抖音 Web 短信验证码登录接口（/passport/web/sms_login/）还原。**全程异步**。

    POST https://login.douyin.com/passport/web/sms_login/

分工（严格按协议边界）：

    Node（nv8 补环境，缺环境时补齐）          Python（唯一 live egress）
    ├── bdms 字节码 → a_bogus                ├── aiohttp：引导会话 / 热身 / 发请求
    └── uc-secure-dtrait-core → 设备指纹     ├── sign / qs / enc / aid-sign（纯 Python）
                                             └── x-tt-session-dtrait（RSA+AES 混合加密）

异步形态（与 send_code 项目一致）：

| 层 | 实现 | 并发安全 |
|---|---|---|
| HTTP 出口 | `aiohttp`（`async with session.post(...)`） | ✅ 天生异步 |
| Node 参数服务 | `asyncio.create_subprocess_exec` + `asyncio.Lock` | ✅ 锁内串行 |
| 浏览器窄工件（可选） | 同步 playwright 放 `asyncio.to_thread` | ✅ 不阻塞事件循环 |
| pyexecjs2（modjs 备用） | `asyncio.to_thread` | ✅ 同上 |

用法（`python main.py` 一句跑完全流程）：
    python main.py                          # 交互式提示输入手机号与验证码，回车即请求
    python main.py --mobile 138xxxxxxxx --code 123456   # 带参则跳过提问
    python main.py --dry-run                # 只生成参数 / URL，不发请求
    python main.py --verbose                # 额外打印完整 URL
    python main.py --abogus-source nv8      # 默认：完全无浏览器

取值优先级：命令行 > 交互输入 > config.local.json > 内置默认（占位号）。
非交互场景（管道 / CI）`input()` 读不到东西时会自动回退到 config / 默认，不会卡住。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import parse_qs

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import dtrait as dtrait_mod
from utils import passport as P
from utils.dtrait_signer import default_signer as dtrait_signer
from utils.logger import logger
from utils.nv8_signer import default_signer as nv8_signer

ROOT = Path(__file__).resolve().parent
DEFAULT_MOBILE = "13800000000"
DEFAULT_CODE = "123456"

# 抓包核对的响应头（风控/票据标记，用于和浏览器响应做同源对照）
GUARD_PREFIX = ("bd-ticket", "x-ms-token", "secure-session", "x-vc-", "bd-tt-error-code")


def _ssl(verify: bool):
    """aiohttp 的 SSL 参数：False = 不校验（本机有 MITM 代理时）。"""
    return None if verify else False


# --------------------------------------------------------------- 1. 会话引导
async def bootstrap(session: aiohttp.ClientSession, verify: bool) -> dict:
    """拿会话态 cookie（ttwid / s_v_web_id / passport_csrf_token …）。

    这些不是算出来的，是服务端下发的：`fp` 与 `x-tt-passport-csrf-token` 都来自它们。

    注意 `ttwid` 由 `ttwid.bytedance.com` 下发，cookie 作用域是那个主机；
    浏览器之外的客户端不会自动把它带到 `login.douyin.com`。
    这里统一用「显式 cookie 字典 + 每次请求显式带上」的写法，绕开作用域问题。
    """
    headers = {
        "User-Agent": P.UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=20)
    jar: dict[str, str] = {}
    for url in (P.HOME, P.LOGIN_HOST + "/"):
        try:
            async with session.get(url, headers=headers, timeout=timeout,
                                   ssl=_ssl(verify)) as resp:
                await resp.read()
                _merge(jar, resp, session, url)
        except Exception as exc:
            logger.warning("%s 访问失败（继续用已有 cookie）: %s", url, exc)

    if not jar.get("ttwid"):
        # `aid` 必须是**整数**，且显式带 Content-Type；
        # 传字符串 aid 会被拒为 {"status_code":1001,"message":"parse params fail"}。
        try:
            async with session.post(
                "https://ttwid.bytedance.com/ttwid/union/register/",
                data=json.dumps({"region": "cn", "aid": int(P.AID), "needFid": False,
                                 "service": "www.ixigua.com",
                                 "migrate_info": {"ticket": "", "source": "node"},
                                 "cbUrlProtocol": "https", "union": True}),
                headers={**headers, "Content-Type": "application/json",
                         "Origin": "https://www.douyin.com",
                         "Referer": "https://www.douyin.com/"},
                timeout=timeout, ssl=_ssl(verify),
            ) as resp:
                await resp.read()
                _merge(jar, resp, session, "https://ttwid.bytedance.com/")
        except Exception as exc:
            logger.warning("ttwid 注册失败: %s", exc)

    logger.info("引导 cookie：%s", json.dumps(
        {k: len(v) for k, v in sorted(jar.items()) if k in
         ("ttwid", "odin_tt", "passport_csrf_token", "s_v_web_id", "msToken", "UIFID")},
        ensure_ascii=False))
    return jar


def _merge(jar: dict, resp: aiohttp.ClientResponse, session: aiohttp.ClientSession,
           url: str) -> None:
    """把响应里的 Set-Cookie 与整个 jar 合进扁平字典（同名后者覆盖）。"""
    for cookie in session.cookie_jar:
        if cookie.key:
            jar[cookie.key] = cookie.value
    for key, morsel in resp.cookies.items():
        jar[key] = morsel.value


def derive_fp(cookies: dict) -> str:
    """fp / verifyFp ← cookie `s_v_web_id`（设备级，页面用它）。"""
    for key in ("s_v_web_id", "webid"):
        value = cookies.get(key)
        if value and value.startswith("verify_"):
            return value
    return P.FP_FALLBACK


def load_cookie_file(path: str) -> dict:
    """支持 4 种写法（storage_state / `{"jar":…}` / 普通 JSON / `k=v; k=v`）。"""
    text = Path(path).read_text(encoding="utf-8").strip()
    jar: dict[str, str] = {}
    if text.startswith("{"):
        data = json.loads(text)
        if "cookies" in data:
            for item in data["cookies"]:
                name, domain = item.get("name"), item.get("domain") or ""
                if not name:
                    continue
                if "douyin" not in domain and not domain.endswith("bytedance.com"):
                    continue
                jar[name] = item.get("value", "")
        else:
            jar = dict(data.get("jar") or data)
    else:
        for part in text.replace("\n", ";").split(";"):
            if "=" in part:
                key, _, value = part.partition("=")
                jar[key.strip()] = value.strip()
    logger.info("从 %s 载入 %d 个 cookie", path, len(jar))
    return jar


def save_cookies(jar: dict, path: str) -> None:
    """把会话 cookie 落盘（凭证；仅显式指定时写，目标应在 js_reverse_cache/private/）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"jar": jar}, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("会话 cookie 已写入 %s（%d 个）", target, len(jar))


# ------------------------------------------------------- 2. 组装签名请求
async def _sign_and_headers(params: dict, body: dict, path: str, cookies: dict,
                            dtrait: str | None = None, ms_token: str | None = None,
                            abogus_fn=None, a_bogus_sync=None) -> tuple[str, str, dict]:
    """签一份 `/passport/web/*` 请求，返回 (url, body_text, headers)。

    参数顺序严格按浏览器抓包：`… device_platform, sign, qs, msToken, a_bogus`。
    `a_bogus` 签的是**字面 query 串**，所以顺序（以及 msToken 在 a_bogus 之前）必须对齐。

    三种 a_bogus 提供方式（优先级从上到下）：
      * `abogus_fn(url) -> signed_url`（协程）：浏览器现场 / nv8 现场；
      * `a_bogus_sync(query) -> value`：pyexecjs2（同步，内部走 to_thread）；
      * 都没有：不带 a_bogus。
    """
    ts = str(params.get("ts") or P.day_ts())
    params.update(P.build_sign(params, body))
    if ms_token:
        params["msToken"] = ms_token
    query = P.serialize_query(params)
    if abogus_fn is not None:
        url = await abogus_fn("%s%s?%s" % (P.LOGIN_HOST, path, query))
    else:
        if a_bogus_sync is not None:
            params["a_bogus"] = await asyncio.to_thread(a_bogus_sync, query)
        url = "%s%s?%s" % (P.LOGIN_HOST, path, P.serialize_query(params))

    headers = {
        "User-Agent": P.UA,
        "Accept": "application/json, text/javascript",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.douyin.com",
        "Referer": "https://www.douyin.com/",
        "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "web-sdk-version": "1",
        "x-tt-passport-aid-sign": P.aid_sign(path, ts=ts),
        "x-tt-passport-trace-id": str(params["biz_trace_id"]),
        "x-tt-passport-verify-portrait": "%s.login" % uuid.uuid4(),
    }
    if cookies.get("passport_csrf_token"):
        headers["x-tt-passport-csrf-token"] = cookies["passport_csrf_token"]
    if dtrait:
        headers["x-tt-session-dtrait"] = dtrait
    return url, P.serialize_body(list(body.items())), headers


async def warm_ms_token(session: aiohttp.ClientSession, cookies: dict,
                        verify: bool = False) -> str | None:
    """先打一个便宜的 `/passport/web/get_qrcode/`，把响应头 `X-Ms-Token` 摘下来。

    为什么需要：浏览器的 `msToken` 是页面里 webmssdk 现场换取的（bdms 会把它自补进 URL）。
    纯 Python 直连 `mssdk.bytedance.com` 拿不到（`resultCode:-2`），
    但**任何一个 `/passport/web/*` 响应都会在 `X-Ms-Token` 里下发一个**。
    """
    params = P.common_params(fp=derive_fp(cookies), ts=P.day_ts(),
                             biz_trace_id=cookies.get("biz_trace_id"))
    params.update({"next": "https://www.douyin.com", "need_short_url": "true",
                   "need_logo": "false", "is_new_login": "1"})
    url, _, headers = await _sign_and_headers(params, {}, P.PATH_GET_QRCODE, cookies,
                                              a_bogus_sync=_modjs_abogus)
    try:
        async with session.get(url, headers=headers, cookies=cookies, timeout=25,
                               ssl=_ssl(verify)) as resp:
            token = resp.headers.get("X-Ms-Token")
            body = await resp.json(content_type=None)
        code = (body.get("data") or {}).get("error_code")
        logger.info("热身 get_qrcode：error_code=%s，msToken=%s", code,
                    ("len=%d" % len(token)) if token else "未下发")
        return token
    except Exception as exc:
        logger.warning("热身拿 msToken 失败（%s）；本次不带 msToken", exc)
        return None


def _modjs_abogus(query: str) -> str:
    """pyexecjs2 + node/mod.js（同步；调用方用 asyncio.to_thread 包）。"""
    from utils.signer import a_bogus
    return a_bogus(query)


async def build_request(mobile: str, code: str, cookies: dict, dtrait: str | None = None,
                        asi: str | None = None, ms_token: str | None = None,
                        abogus_fn=None, a_bogus_sync=None) -> tuple[str, str, dict, dict]:
    """产出 (url, body_text, headers, params)。"""
    params = P.common_params(fp=derive_fp(cookies), asi=asi, ts=P.day_ts(),
                             biz_trace_id=cookies.get("biz_trace_id"))
    body = P.body_sms_login(mobile, code)
    token = ms_token or cookies.get("msToken")
    url, body_text, headers = await _sign_and_headers(
        params, body, P.PATH_SMS_LOGIN, cookies, dtrait, ms_token=token,
        abogus_fn=abogus_fn, a_bogus_sync=a_bogus_sync)
    params["a_bogus"] = url.rsplit("a_bogus=", 1)[-1]
    return url, body_text, headers, params


# ------------------------------------------------------------------- 3. 入口
def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning("config 解析失败（忽略）: %s", exc)
        return {}


def _ask(label: str, supplied: str | None, configured: str | None, fallback: str) -> str:
    """取值优先级：命令行 > 交互输入 > config.local.json > 内置默认。"""
    if supplied:
        return supplied.strip()
    try:
        value = input(label).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        value = ""
    return value or (configured or fallback).strip()


def _print_request(url: str, body: str, headers: dict, verbose: bool) -> None:
    print("\n" + "=" * 78)
    print("目标接口 :", P.SMS_LOGIN_URL)
    print("表单数据 :", body)
    print("请求头   :")
    for key, value in headers.items():
        shown = value if len(value) <= 76 else "%s…（共 %d 字符）" % (value[:76], len(value))
        print("           %-30s %s" % (key, shown))
    query = url.split("?", 1)[1]
    print("查询字符串: %s…（共 %d 字符 / %d 个参数）"
          % (query[:76], len(url), len(parse_qs(query, keep_blank_values=True))))
    if verbose:
        print("\n完整 URL：\n" + url)
    print("=" * 78)


async def _prepare_dtrait(args, cookies: dict) -> str | None:
    """组 `x-tt-session-dtrait`：优先级 `--dtrait-file` > 外部服务 > 本地 nv8。"""
    if args.dtrait_file:
        logger.info("dtrait：使用外部给定的值")
        return Path(args.dtrait_file).read_text(encoding="utf-8").strip()
    if args.no_dtrait:
        return None
    payload = None
    if args.dtrait_service:
        payload = await asyncio.to_thread(_fetch_dtrait_service, args.dtrait_service)
    if payload is None:
        try:
            payload = await dtrait_signer().payload()
        except Exception as exc:
            logger.warning("nv8 采集 dtrait 失败（%s）；本次不带该头", exc)
            return None
    value = dtrait_mod.build(payload)
    version, wrap, body = value.split("_")
    logger.info("dtrait：str=%d 非零=%d 段长=%s（浏览器参考 2/344/472）",
                len(payload.get("str", {})),
                sum(1 for v in payload.get("str", {}).values() if v not in (0, "0")),
                [len(version), len(wrap), len(body)])
    return value


def _fetch_dtrait_service(service_url: str) -> dict | None:
    """从 send_code 常驻工件服务取 dtrait payload（可选路径）。"""
    try:
        req = urllib.request.Request(service_url.rstrip("/") + "/dtrait",
                                     data=b"", method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=120).read()).get("payload")
    except Exception as exc:
        logger.warning("取 dtrait payload 失败（%s）", exc)
        return None


async def _amain() -> int:
    parser = argparse.ArgumentParser(
        description="抖音 Web 短信登录接口还原（默认无参数直接跑完全流程，全程异步）")
    parser.add_argument("--mobile", help="手机号（11 位，不带 +86）；给了就不提问")
    parser.add_argument("--code", help="短信验证码；给了就不提问")
    parser.add_argument("--dry-run", action="store_true", help="只生成参数与 URL，不发请求")
    parser.add_argument("--verbose", action="store_true", help="打印完整 URL")
    parser.add_argument("--verify-tls", action="store_true",
                        help="严格校验 TLS（本机有 MITM 代理时默认关闭）")
    parser.add_argument("--cookie-file", help="cookie 文件（storage_state / JSON / `k=v; k=v`）")
    parser.add_argument("--save-cookies", help="把本次会话 cookie 落盘（凭证，仅显式指定时写）")
    parser.add_argument("--dtrait-file", help="直接给一个现成的 x-tt-session-dtrait 值（对照实验用）")
    parser.add_argument("--dtrait-service", default="",
                        help="改成向 send_code 工件服务要 dtrait payload（默认用本地 nv8）")
    parser.add_argument("--no-dtrait", action="store_true", help="不带 x-tt-session-dtrait")
    parser.add_argument("--no-warm", action="store_true",
                        help="跳过热身（不从 get_qrcode 的响应头摘 msToken）")
    parser.add_argument("--abogus-source", choices=("nv8", "browser", "modjs"), default="nv8",
                        help="a_bogus 来源（默认 nv8，**完全无浏览器、实测登录成功**）："
                             "nv8=页面同款 bdms 字节码 + nv8 补环境；"
                             "browser=真实浏览器 bdms 现场签名（需 playwright）；"
                             "modjs=pyexecjs2+node/mod.js（公开移植版，服务端不认）")
    parser.add_argument("--browser-state",
                        default=str(ROOT / "js_reverse_cache" / "private" / "browser_state.json"),
                        help="--abogus-source browser 用的浏览器会话状态（storage_state）")
    parser.add_argument("--config", default=str(ROOT / "config.local.json"))
    parser.add_argument("--json-out", help="把响应写成 JSON 文件（后端/上层调用用；见 android/AGENTS.md 接口契约）")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    mobile = _ask("请输入手机号（11 位，不带 +86）：", args.mobile,
                  config.get("mobile"), DEFAULT_MOBILE)
    code = _ask("请输入短信验证码：", args.code, config.get("code"), DEFAULT_CODE)
    if not (len(mobile) == 11 and mobile.isdigit()):
        print("手机号 %r 格式不对（应为 11 位数字），转为 dry-run。" % mobile)
        args.dry_run = True

    verify = bool(args.verify_tls or config.get("verify_tls"))
    cookie_file = args.cookie_file or config.get("cookie_file")

    browser = None
    try:
        async with aiohttp.ClientSession() as session:
            cookies: dict[str, str] = {}
            if cookie_file:
                cookies.update(load_cookie_file(cookie_file))
            cookies.update(await bootstrap(session, verify))

            # a_bogus 来源：nv8（默认）/ browser / modjs
            abogus_fn = None
            a_bogus_sync = None
            if args.abogus_source == "nv8":
                _body = P.serialize_body(list(P.body_sms_login(mobile, code).items()))

                async def _nv8(u: str, _b: str = _body) -> str:
                    # 只取 nv8/bdms 的 a_bogus，拼回我们自己的 query。
                    # （nv8 的 signedUrl 还会被 webmssdk 补上 X-Bogus / 第二个 msToken，
                    #   浏览器并不发这些，直接用会把参数集弄脏。）
                    r = await nv8_signer().abogus(u, "POST", _b)
                    return "%s&a_bogus=%s" % (u, r["a_bogus"])

                abogus_fn = _nv8
                logger.info("a_bogus：nv8 里的 bdms（无浏览器，首次冷启动 ~5s）")
            elif args.abogus_source == "browser":
                from utils.browser_artifacts import AsyncBrowserArtifacts, available
                if not available():
                    logger.warning("没装 playwright，回退到 --abogus-source nv8")
                    args.abogus_source = "nv8"
                else:
                    # 原生 async playwright（与 send_code 的 AsyncBrowserAbogus 同形态）
                    browser = await AsyncBrowserArtifacts(
                        state_file=args.browser_state, headless=True).__aenter__()
                    cookies.update(await browser.cookies())
                    _body = P.serialize_body(list(P.body_sms_login(mobile, code).items()))

                    async def _browser(u: str, _b: str = _body) -> str:
                        return (await browser.sign(u, "POST", _b))["url"]

                    abogus_fn = _browser
                    logger.info("a_bogus：浏览器 bdms 现场生成（%d 个 cookie 的会话）", len(cookies))
            if args.abogus_source == "modjs":
                a_bogus_sync = _modjs_abogus
                logger.info("a_bogus：pyexecjs2 + node/mod.js（公开移植版）")

            if args.save_cookies:
                save_cookies(cookies, args.save_cookies)

            dtrait = await _prepare_dtrait(args, cookies)
            ms_token = None if args.no_warm else await warm_ms_token(session, cookies, verify)

            url, body, headers, params = await build_request(
                mobile, code, cookies, dtrait=dtrait, ms_token=ms_token,
                abogus_fn=abogus_fn, a_bogus_sync=a_bogus_sync)
            logger.info("a_bogus：%d 字符", len(params["a_bogus"]))
            _print_request(url, body, headers, args.verbose)

            dump = ROOT / "output" / "last_request.json"
            dump.parent.mkdir(exist_ok=True)
            dump.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            logger.info("请求快照已写入 %s", dump)

            if args.dry_run:
                print("\n[dry-run] 未发送请求。去掉 --dry-run 即真正请求。")
                return 0

            logger.info("向 %s 发送短信登录请求…", mobile[:3] + "****" + mobile[-2:])
            async with session.post(url, data=body, headers=headers, cookies=cookies,
                                    timeout=aiohttp.ClientTimeout(total=25),
                                    ssl=_ssl(verify)) as resp:
                text = await resp.text()
                status = resp.status
                ctype = resp.headers.get("content-type")
                guard = {k: v for k, v in resp.headers.items()
                         if k.lower().startswith(GUARD_PREFIX)}
                if args.save_cookies:
                    cookies.update({k: m.value for k, m in resp.cookies.items()})
                    save_cookies(cookies, args.save_cookies)

        print("\n" + "-" * 78)
        print("HTTP 状态码 :", status)
        print("Content-Type:", ctype)
        if guard:
            print("风控/票据响应头 :")
            for key, value in guard.items():
                print("   %-40s %s" % (key, value[:110]))
        print("-" * 78)
        try:
            parsed = json.loads(text)
            print(json.dumps(parsed, ensure_ascii=False, indent=2)[:4000])
            err = (parsed.get("data") or {}).get("error_code")
            print("-" * 78)
            if parsed.get("message") == "success":
                names = [k for k in ("sessionid", "sessionid_ss", "sid_guard", "uid_tt")
                         if k in cookies]
                print("业务 error_code :", err, "→ 登录成功；会话 cookie:", names or "（已在 jar 中）")
            else:
                print("业务 error_code :", err,
                      "（1203=验证码错误/过期；7=码有效但请求被风控挡下（a_bogus 不对）；"
                      "2156=风控拦截）")
        except ValueError:
            parsed = None
            print(text[:2000])
        if args.json_out:
            Path(args.json_out).write_text(json.dumps({
                "status": status, "content_type": ctype, "headers": guard, "json": parsed,
                **({"text": text[:4000]} if parsed is None else {}),
            }, ensure_ascii=False), encoding="utf-8")
        print("-" * 78)
        return 0
    finally:
        if browser is not None:
            await browser.__aexit__(None, None, None)
        await dtrait_signer().close()
        if args.abogus_source == "nv8":
            await nv8_signer().close()


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
