r"""main.py —— 抖音 Web 发送短信验证码接口（/passport/web/send_code/）的完整请求链路。

分工（严格按协议的边界）：

    Node（nv8 沙箱，缺环境时补齐）           Python（唯一 live egress）
    ├── uc-secure-dtrait-core → 设备指纹     ├── 组装 query / body / headers
    └── a_bogus 签名器                       ├── sign / qs / enc / aid-sign
                                             ├── x-tt-session-dtrait（RSA+AES 混合加密）
                                             └── POST 目标接口并打印响应

用法：
    python main.py                       # 直接跑完全流程：生成参数 → 请求 → 打印响应
    python main.py --dry-run             # 只生成参数，不发请求
    python main.py --mobile 138xxxxxxxx  # 换目标号码（覆盖 config.local.json）
    python main.py --verbose             # 额外打印完整 URL

参数优先级：命令行 > config.local.json > 内置默认（非可投递占位号）。
全程不问控制台，`python main.py` 一句就能跑完。

⚠️ 该接口会给目标号码发**真实短信**（并消耗风控额度）。
   默认占位号不指向真实用户；换成真号前请确认那是你自己的号码。
   建议用项目自带运行时 `runtime/run.py`（等价，但保证用项目自己的 venv + node）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import dtrait as dtrait_mod
from utils.logger import logger, log_json
from utils.passport import AID, APP_KEY, aid_sign, build_sign, enc
from utils.signer import AsyncNodeSigner

SEND_CODE_PATH = "/passport/web/send_code/"
SEND_CODE_URL = "https://login.douyin.com" + SEND_CODE_PATH
HOME = "https://www.douyin.com/"

# 内置默认值：非可投递占位号，保证 `python main.py` 能直接跑完且不骚扰真实用户。
DEFAULT_MOBILE = "13800000000"   # 占位号；交互式终端下 _amain() 会提示输入
DEFAULT_COOKIE_FILE = "js_reverse_cache/private/browser_state.json"
DEFAULT_BROWSER_STATE = "js_reverse_cache/private/browser_env_live2.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# 抓包里的 account_sdk_source_info（enc 过的浏览器环境 JSON）。
# 它只描述运行环境，属"半固定"参数：换机器/换指纹时才需要重算。
ASI_FALLBACK = (
    "7e276d64776172647760466a6b66707777606b667c273f3731292772606761776c736077273f63646976602927"
    "666d776a686061776c736077273f63646976602927666d60696961776c736077273f63646976602927756970626c"
    "6b76273f3029276c6b6b60774d606c626d71273f3c3d3029276c6b6b6077526c61716d273f343c353129276a70"
    "7160774d606c626d71273f373d29276a70716077526c61716d273f34333529277260676269273f7e2773606b616a"
    "77273f27426a6a626960254c6b662b252d4b534c414c442c27292777606b6160776077273f27444b424940252d"
    "4b534c414c4429254b534c414c44254260436a7766602557515d253135333525516c252d357d35353535373d3536"
    "2c25416c77606671364134342573765a305a352575765a305a35292541364134342c277829276470716a6864716c"
    "6a6b273f7e2776273f27353535353535353527292766273f2735353535353427292775273f2735353535353535272927"
    "7634273f2735353535353535352729276634273f27353535352729277534273f273527782927756077636a776864"
    "6b6660273f7e27716c68604a776c626b273f34323d3c33363332363c3735352927707660614f564d606475566c7f"
    "60273f36303130373333323629276b64736c6264716c6a6b516c686c6b62273f7e276160666a616061476a617c56"
    "6c7f60273f3c3c373236372927606b71777c517c7560273f276b64736c6264716c6a6b2729276c6b6c716c64716a77"
    "517c7560273f276b64736c6264716c6a6b2729276b646860273f276d717175763f2a2a7272722b616a707c6c6b2b"
    "666a682a27292777606b61607747696a666e6c6b62567164717076273f276b6a6b2867696a666e6c6b6227292776"
    "6077736077516c686c6b62273f2766616b286664666d602960616260296a776c626b296c6b6b60772971715a6462"
    "72272927627069605671647771273f34353d362b333c3c3c3c3c3c3d3d35323c29276270696041707764716c6a6b"
    "273f276b6a6b60277878292767776a72766077273f7e2771273f273c31323430323336333c3d3234272927676c71"
    "5a75776a716a666a69273f276364697660272927676c715a6d6069756077273f63646976607878"
)


def day_ts(now: datetime | None = None) -> str:
    """当天 12:00 UTC 的秒级时间戳（sign 与 aid-sign 共用，整天不变）。"""
    now = now or datetime.now(timezone.utc)
    return str(int(datetime(now.year, now.month, now.day, 12, 0, 0, tzinfo=timezone.utc).timestamp()))


# --------------------------------------------------------------- 1. 会话引导
def _ssl_arg(verify: bool):
    """aiohttp 的 SSL 参数：False = 不校验（本机有 MITM 代理时）。"""
    return None if verify else False


def read_cookies(session: aiohttp.ClientSession) -> dict:
    """从 aiohttp 的 cookie jar 里读出抖音域下的 cookie。"""
    jar: dict[str, str] = {}
    for url in ("https://login.douyin.com/", "https://www.douyin.com/", "https://douyin.com/"):
        try:
            for key, morsel in session.cookie_jar.filter_cookies(aiohttp.client.URL(url)).items():
                if key:
                    jar[key] = morsel.value
        except Exception:
            pass
    return jar


async def bootstrap_session(session: aiohttp.ClientSession, verify: bool = False) -> dict:
    """先访问主页拿基础 cookie（ttwid / odin_tt / passport_csrf_token …）。

    这些是“会话态”参数：不是算出来的，是服务端下发的，必须现场取。
    ttwid 由专门的 register 接口下发，需要单独请求一次。全链路异步（aiohttp）。
    """
    headers = {
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    ssl_arg = _ssl_arg(verify)
    timeout = aiohttp.ClientTimeout(total=20)
    for url in (HOME, "https://login.douyin.com/"):
        try:
            async with session.get(url, headers=headers, timeout=timeout, ssl=ssl_arg) as resp:
                await resp.read()
        except Exception as exc:
            logger.warning("%s 访问失败（继续用已有 cookie）: %s", url, exc)

    # ttwid：抖音 Web 的必需设备 cookie，由 union register 接口下发
    if "ttwid" not in read_cookies(session):
        try:
            async with session.post(
                "https://ttwid.bytedance.com/ttwid/union/register/",
                json={
                    "region": "cn", "aid": AID, "needFid": False,
                    "service": "www.ixigua.com", "migrate_info": {"ticket": "", "source": "node"},
                    "cbUrlProtocol": "https", "union": True,
                },
                headers=headers, timeout=timeout, ssl=ssl_arg,
            ) as resp:
                await resp.read()
        except Exception as exc:
            logger.warning("ttwid 注册失败: %s", exc)

    cookies = read_cookies(session)
    got = {k: len(v) for k, v in cookies.items()}
    logger.info("引导 cookie：%s", json.dumps(got, ensure_ascii=False))
    return cookies


def derive_fp(cookies: dict) -> str:
    """设备指纹 fp/verifyFp：优先用 cookie 里的 s_v_web_id，否则退回抓包值。"""
    for key in ("s_v_web_id", "webid"):
        value = cookies.get(key)
        if value and value.startswith("verify_"):
            return value
    return "verify_ms9z317l_z7J09WzZ_FQJb_4CGd_91Kx_IYzv6iWtvu7B"


def load_browser_env(path: str | Path) -> dict:
    """从「浏览器真实抓包」里导出环境参数，供我们的请求使用。

    为什么需要：`fp` / `account_sdk_source_info` / `msToken` 是**运行环境特有**的，
    由页面上的 SDK 现场生成（或服务端下发），我们无法凭空算出与之完全一致的值。
    把它们从浏览器现场导出后，签名/时间戳/一次项仍然由我们自己生成。

    输入：本工具 `get_network_request(outputFile=...)` 导出的请求快照 JSON。
    返回：{fp, asi, msToken, request_host, portrait, dtrait}
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = data[0]
    from urllib.parse import parse_qs, urlparse

    raw_query = urlparse(data["url"]).query
    params = {k: v[0] for k, v in parse_qs(raw_query, keep_blank_values=True).items()}
    headers = {h["name"].lower(): h["value"] for h in data.get("requestHeadersArray", [])}
    return {
        "fp": params.get("fp"),
        "asi": params.get("account_sdk_source_info"),
        "msToken": params.get("msToken"),
        "request_host": params.get("request_host"),
        # 这两个是“设备/会话级”的，我们无法凭空算出与浏览器一致的取值；
        # 导进来就能把“是不是它们导致 2156”隔离出来。
        "portrait": headers.get("x-tt-passport-verify-portrait"),
        "dtrait": headers.get("x-tt-session-dtrait"),
    }


# ------------------------------------------------------- 2. 组装全部签名参数
async def build_request(mobile: str, cookies: dict, signer,
                        env: dict | None = None,
                        abogus_fn=None) -> tuple[str, str, dict]:
    """产出 (url, body, headers)。

    env 非空时，里面的 fp / asi / msToken / request_host 会覆盖默认值
    （即“把浏览器环境导进来用”）。
    """
    env = env or {}
    fp = env.get("fp") or derive_fp(cookies)
    asi = env.get("asi") or ASI_FALLBACK
    # 浏览器是双重编码（%253A%252F…）。注意：`load_browser_env` 给出的是 decode 一次后的值，
    # 不能直接用（那会变成单重编码），所以这里统一自己双编码。
    request_host = quote(quote("https://www.douyin.com", safe=""), safe="")
    ts = day_ts()

    # biz_trace_id：浏览器里 **cookie / query 参数 / x-tt-passport-trace-id 头三者取值相同**。
    # 我们之前只随机生成 query/头，cookie 却是导进来的旧值 → 三者不一致。
    biz_trace_id = cookies.get("biz_trace_id") or ("%08x" % random.getrandbits(32))

    # 半固定参数（顺序与抓包一致，sign 只吃排序后前 10 个）
    params: dict[str, object] = {
        "passport_jssdk_version": "3.4.4",
        "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": 1,
        "aid": AID,
        "language": "zh",
        "account_app_language": "zh-CN",
        "ts": ts,
        "is_from_iesaccountsaas": 1,
        "p_ui": "2.4.4",
        "p_ca": "4.0.26",
        "p_ca_real": "1.0.0.910",
        "fp": fp,
        "verifyFp": fp,
        "account_sdk_source": "web",
        "account_sdk_source_info": asi,
        "p_js_v": "3.4.4",
        "p_js_t": "pro",
        "p_zt": "3.3.25",
        "p_ver": "1.1.3",
        "p_ver_real": "0",
        "request_host": request_host,
        "p_bd": "1.0.1.19-fix.01",
        # 动态参数（每次请求都变）
        "p_ts": int(time.time() * 1000),
        "p_no": "%064x" % random.getrandbits(256),
        "biz_trace_id": biz_trace_id,
        "device_platform": "web_app",
    }

    # body：mobile / type 都是 enc(hex(utf8 XOR 0x05))
    body_items = [
        ("is6Digits", "1"),
        ("mix_mode", "1"),
        ("mobile", enc("+86 " + mobile)),
        ("type", enc("24")),
        ("fixed_mix_mode", "1"),
    ]
    body = dict(body_items)

    # 签名：sign + qs（依赖 params 与 body 的排序）
    params.update(build_sign(params, body))

    # msToken：优先用导出的浏览器环境值，其次 cookie（服务端也会在响应头 X-Ms-Token 下发）
    ms_token = env.get("msToken") or cookies.get("msToken")
    if ms_token:
        params["msToken"] = ms_token

    # a_bogus：对「不含 a_bogus 的 query」签名（Node 侧生成）
    query = "&".join("%s=%s" % (k, v) for k, v in params.items())
    # a_bogus：默认交给 nv8 里的 bdms；也可注入外部生成器（浏览器工件形态）
    signed_url = "%s?%s" % (SEND_CODE_URL, query)
    body_text_for_sign = "&".join("%s=%s" % (k, v) for k, v in body_items)
    final_url = signed_url
    if abogus_fn is not None:
        # 浏览器形态：bdms 可能自己补参数（如 msToken），必须用返回的**完整 URL**
        final_url = await abogus_fn(signed_url, "POST", body_text_for_sign)
        logger.info("a_bogus：已由浏览器工件生成（URL %d 字符）", len(final_url))
    else:
        # 注意：send_code 是 POST 且有 body，两者都参与 a_bogus。
        # 2026-09-18 修：以前这里漏了 method/body（默认 GET/None），签的对象就是错的。
        # 但修完实测本端点仍返回 2156 —— 即 nv8 这条链路在 /send_code/ 上不被接受
        # （同一个 nv8 链路在 /passport/web/sms_login/ 上是被接受的）。
        a_bogus = await signer.a_bogus(url=signed_url, user_agent=UA, uifid=cookies.get("UIFID"),
                                       method="POST", body=body_text_for_sign)
        logger.info("a_bogus：%d 字符（bdms/nv8）", len(a_bogus))
        params["a_bogus"] = a_bogus
        final_url = "%s?%s" % (SEND_CODE_URL, "&".join("%s=%s" % (k, v) for k, v in params.items()))

    body_text = "&".join("%s=%s" % (k, v) for k, v in body_items)

    # 头部签名：x-tt-passport-aid-sign（HKDF + HMAC，纯 Python，已逐位验证）
    # x-tt-session-dtrait：每次现场采集 payload 再混合加密（Node 采集 + Python 加密）；
    # 若 --browser-env 导入了浏览器的 dtrait，则优先用它（用于隔离实验）。
    if env.get("dtrait"):
        dtrait_value = env["dtrait"]
        logger.info("dtrait：使用浏览器导出值")
    else:
        payload = await signer.dtrait_payload()
        dtrait_value = dtrait_mod.build(payload)
        logger.info("dtrait payload：str=%d（非零 %d）bool=%d",
                    len(payload.get("str", {})),
                    sum(1 for v in payload.get("str", {}).values() if v not in (0, "0")),
                    len(payload.get("bool", {})))

    trace_id = params["biz_trace_id"]
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/javascript",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.douyin.com",
        "Referer": "https://www.douyin.com/",
        # UA-CH：声明自己是 Chrome 153 就必须带全，否则是典型的“不一致”机器人特征
        "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "web-sdk-version": "1",
        "x-tt-passport-aid-sign": aid_sign(SEND_CODE_PATH, ts=ts),
        "x-tt-passport-trace-id": trace_id,
        "x-tt-passport-verify-portrait": env.get("portrait") or ("%s.login" % random_uuid()),
        "x-tt-session-dtrait": dtrait_value,
    }
    csrf = cookies.get("passport_csrf_token")
    if csrf:
        headers["x-tt-passport-csrf-token"] = csrf

    return final_url, body_text, headers


async def _service_health(base: str, session: aiohttp.ClientSession, timeout: float = 3.0) -> dict | None:
    try:
        async with session.get(base + "/health", timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        return None
    return None


async def _ensure_service(args) -> str | None:
    """确保常驻工件服务可用：已有则直接用；没有就自动拉起（脱附）。

    这是默认（auto）形态的实现：第一次付 ~3s 启服务，之后每次调用只 ~0.7s，
    比每次启浏览器的 ~3.5s 更快也更稳定。
    """
    base = args.service_url.rstrip("/")
    async with aiohttp.ClientSession() as probe:
        if await _service_health(base, probe):
            return base
        if args.no_autostart:
            return None

        port = aiohttp.client.URL(base).port or 8787
        log_path = Path(__file__).resolve().parent / "js_reverse_cache" / "private" / "artifact_service.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("未发现工件服务，自动拉起（port=%d pages=%d，首次 ~3s）…", port, args.service_pages)
        try:
            log = open(log_path, "ab")
            cmd = [sys.executable, "-m", "utils.artifact_service",
                   "--port", str(port), "--pages", str(args.service_pages)]
            if os.name == "nt":
                flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent),
                                 stdout=log, stderr=log, creationflags=flags, close_fds=True)
            else:
                subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent),
                                 stdout=log, stderr=log, start_new_session=True)
        except Exception as exc:
            logger.warning("拉起工件服务失败: %s", exc)
            return None

        deadline = time.time() + 60
        while time.time() < deadline:
            await asyncio.sleep(0.5)
            if await _service_health(base, probe):
                logger.info("工件服务就绪：%s", base)
                return base
        logger.warning("工件服务在 60s 内未就绪（日志：%s）", log_path)
        return None


async def _run_with_service(args, mobile, browser_env, verify, signer, service_url: str) -> int:
    """调用常驻工件服务（浏览器/Node 只启一次，每次调用毫秒级）。"""
    base = service_url.rstrip("/")
    session = aiohttp.ClientSession()
    try:
        async with session.get(base + "/health",
                              timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                raise RuntimeError("工件服务不可用：HTTP %d" % resp.status)
            health = await resp.json()
        logger.info("工件服务就绪：%s", json.dumps(health, ensure_ascii=False))

        async with session.get(base + "/cookies",
                              timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
        cookies = data.get("cookies") or {}
        logger.info("浏览器会话（工件服务）：%d 个 cookie", len(cookies))
        set_cookies(session, cookies)
        if args.cookie_file:
            await load_cookies(session, args.cookie_file)

        async def remote_abogus(url: str, method: str, body: str | None) -> str:
            async with session.post(base + "/abogus", json={"url": url, "method": method, "body": body},
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
            if r.status != 200 or "signed_url" not in data:
                raise RuntimeError("工件服务返回异常：%s" % data)
            logger.info("a_bogus：工件服务 %.1fms（URL %d 字符）", data.get("ms", 0), len(data["signed_url"]))
            return data["signed_url"]

        url, body, headers = await build_request(mobile, cookies, signer, env=browser_env,
                                                 abogus_fn=remote_abogus)
        return await _finish(args, mobile, session, url, body, headers, verify, signer)
    finally:
        await session.close()


async def _run_with_browser_abogus(args, mobile, browser_env, verify, signer) -> int:
    """浏览器工件形态（异步）：浏览器只产 a_bogus（拦下 send），Python 独占 HTTP 出口。"""
    from utils.browser_abogus import AsyncBrowserAbogus

    logger.info("启动浏览器生成 a_bogus（只取窄工件，不发业务请求）…"
                "（默认来源；要完全无浏览器请加 --abogus-source nv8）")
    async with AsyncBrowserAbogus(state_file=args.browser_state) as bab:
        cookies = await bab.cookies()
        logger.info("浏览器会话：%d 个 cookie", len(cookies))
        session = aiohttp.ClientSession()
        try:
            set_cookies(session, cookies)
            if args.cookie_file:
                await load_cookies(session, args.cookie_file)
            url, body, headers = await build_request(mobile, cookies, signer, env=browser_env,
                                                     abogus_fn=bab.signed_url)
            # 浏览器已关闭后，下面全部由 Python（aiohttp）发出
            return await _finish(args, mobile, session, url, body, headers, verify, signer)
        finally:
            await session.close()


def random_uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def set_cookies(session: aiohttp.ClientSession, jar: dict[str, str]) -> None:
    """把 cookie 写进 aiohttp 的 cookie jar（同时挂到 douyin 两个域）。"""
    for url in ("https://login.douyin.com/", "https://www.douyin.com/"):
        session.cookie_jar.update_cookies(jar, response_url=aiohttp.client.URL(url))


async def load_cookies(session: aiohttp.ClientSession, path: str) -> None:
    """加载外部 cookie（异步）。

    支持三种写法：
      1. Playwright storage_state：{"cookies": [{name, value, domain, ...}], "origins": [...]}
      2. 普通 JSON：{"k": "v"}
      3. Header 文本：`k=v; k=v`
    """
    text = Path(path).read_text(encoding="utf-8").strip()
    jar: dict[str, str] = {}
    if text.startswith("{"):
        data = json.loads(text)
        if "cookies" in data:
            kept = skipped = 0
            for item in data["cookies"]:
                name = item.get("name")
                domain = item.get("domain") or ""
                if not name:
                    continue
                # 只保留抖音域下的 cookie（导出的是整个浏览器，含 jd/taobao 等无关域）
                if "douyin" not in domain and not domain.endswith("bytedance.com"):
                    skipped += 1
                    continue
                jar[name] = item.get("value", "")
                kept += 1
            logger.info("cookie 过滤：保留 %d 个抖音域，跳过 %d 个其他域", kept, skipped)
        else:
            jar = dict(data)
    else:
        for part in text.replace("\n", ";").split(";"):
            if "=" in part:
                key, _, value = part.partition("=")
                jar[key.strip()] = value.strip()
    set_cookies(session, jar)
    logger.info("从 %s 载入 %d 个 cookie", path, len(jar))


# ------------------------------------------------------------------- 3. 入口
def _silence_insecure_warning() -> None:
    """关掉 urllib3 的 InsecureRequestWarning。

    本机走了一个 127.0.0.1 上的中间人代理（企业/调试代理），它的根证书不在
    certifi 里，所以对 douyin 只能 verify=False。这是**有意的**，不需要每次刷警告。
    （要恢复严格校验：加 --verify-tls，届时也不会再走这条分支。）
    """
    try:
        import urllib3
        from urllib3.exceptions import InsecureRequestWarning

        urllib3.disable_warnings(InsecureRequestWarning)
    except Exception:  # pragma: no cover - urllib3 一定随 requests 安装
        pass


def load_config(path: Path) -> dict:
    """读 config.local.json（不存在就返回空）。

    就是让 `python main.py` 一句命令能直接跑完，不用在控制台输任何参数。
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning("config.local.json 解析失败（忽略）: %s", exc)
        return {}


async def _amain() -> int:
    parser = argparse.ArgumentParser(
        description="抖音 Web 发送短信验证码接口逆向调用（默认无参数直接跑完全流程）",
        epilog="不带任何参数 = 读 config.local.json（缺省用占位号），生成参数并直接请求，打印响应。",
    )
    parser.add_argument("--mobile", help="目标手机号（不带 +86）；不填则在终端里 input() 输入")
    parser.add_argument("--dry-run", action="store_true", help="只生成参数与 URL，不发请求")
    parser.add_argument("--verbose", action="store_true", help="打印完整 URL")
    parser.add_argument("--verify-tls", action="store_true",
                        help="严格校验 TLS 证书（本机有 MITM 代理时默认关闭）")
    parser.add_argument("--cookie-file", help="从文件加载 cookie（Header 文本 / JSON / storage_state）")
    parser.add_argument("--abogus-source", choices=("auto", "service", "browser", "nv8"), default="auto",
                        help="a_bogus 来源（默认 auto）："
                             "auto=有常驻服务就用它、没有就自动拉起（最快且最稳）；"
                             "service=必须已有常驻服务；browser=每次启无头浏览器；"
                             "nv8=完全无浏览器（**实测本端点拒收：2156**，见 README；"
                             "同一 nv8 链路在 sms_login 项目上是被接受的）")
    parser.add_argument("--service-url", default="http://127.0.0.1:8787",
                        help="常驻工件服务地址（默认 http://127.0.0.1:8787）")
    parser.add_argument("--service-pages", type=int, default=4,
                        help="自动拉起工件服务时的页面池大小（默认 4；越大启动越慢）")
    parser.add_argument("--no-autostart", action="store_true",
                        help="auto 模式下不自动拉起工件服务（不可用则回退到 browser）")
    parser.add_argument("--browser-state", default=str(DEFAULT_BROWSER_STATE),
                        help="browser 形态使用的浏览器会话状态文件（storage_state JSON）")
    parser.add_argument("--browser-env",
                        help="从浏览器真实抓包快照导出环境（fp / account_sdk_source_info / msToken）并用之")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.local.json"),
                        help="配置文件路径（默认 config.local.json）")
    parser.add_argument("--json-out", help="把响应写成 JSON 文件（后端/上层调用用）")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    # 手机号来源优先级：--mobile > config.local.json > 终端 input()
    mobile = (args.mobile or config.get("mobile") or "").strip()
    if not mobile:
        # 主路径：让用户用 input() 输入手机号。
        # 非交互场景（管道为空 / IDE / CI）input() 会抛 EOFError，此时回退到占位号。
        try:
            mobile = input("请输入手机号码：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            if not sys.stdin or not sys.stdin.isatty():
                print("未读到手机号（非交互输入），改用内置占位号 %s。" % DEFAULT_MOBILE)
            mobile = ""
        if not mobile:
            mobile = DEFAULT_MOBILE
    if not (len(mobile) == 11 and mobile.isdigit()):
        print("手机号 %r 格式不对（应为 11 位数字），转为 dry-run。" % mobile)
        args.dry_run = True

    verify = bool(args.verify_tls or config.get("verify_tls"))
    if not verify:
        _silence_insecure_warning()

    cookie_file = args.cookie_file or config.get("cookie_file") or ""
    cookie_path = Path(cookie_file) if cookie_file else Path(DEFAULT_COOKIE_FILE)

    if mobile == DEFAULT_MOBILE:
        print("ℹ 当前用内置占位号 %s（不指向真实用户）；"
              "要换号请改 config.local.json 的 mobile 或加 --mobile。" % DEFAULT_MOBILE)

    browser_env = load_browser_env(args.browser_env) if args.browser_env else None

    session = aiohttp.ClientSession()
    signer = AsyncNodeSigner()
    try:
        if cookie_path.exists():
            await load_cookies(session, str(cookie_path))
        cookies = await bootstrap_session(session, verify=verify)

        if args.abogus_source == "auto":
            base = await _ensure_service(args)
            if base:
                return await _run_with_service(args, mobile, browser_env, verify, signer, base)
            logger.warning("工件服务不可用，回退到 browser 形态（每次启无头浏览器）")
            return await _run_with_browser_abogus(args, mobile, browser_env, verify, signer)

        if args.abogus_source == "service":
            return await _run_with_service(args, mobile, browser_env, verify, signer, args.service_url)

        if args.abogus_source == "browser":
            return await _run_with_browser_abogus(args, mobile, browser_env, verify, signer)

        url, body, headers = await build_request(mobile, cookies, signer, env=browser_env)
        if browser_env:
            logger.info("已从浏览器环境导出：fp=%s… asi=%d 字符 msToken=%s",
                        (browser_env.get("fp") or "-")[:24],
                        len(browser_env.get("asi") or ""),
                        "有" if browser_env.get("msToken") else "无")
        return await _finish(args, mobile, session, url, body, headers, verify, signer)
    finally:
        await signer.close()
        await session.close()


def main() -> int:
    """同步入口：全流程在 asyncio 事件循环里异步执行。"""
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130


async def _finish(args, mobile, session, url, body, headers, verify, signer) -> int:
    """打印请求、落盘快照、按需发送并打印响应（两种 a_bogus 来源共用）。"""
    print("\n" + "=" * 78)
    print("目标接口 :", SEND_CODE_URL)
    print("表单数据 :", body)
    print("请求头   :")
    for key, value in headers.items():
        shown = value if len(value) <= 76 else "%s…（共 %d 字符）" % (value[:76], len(value))
        print("           %-28s %s" % (key, shown))
    print("查询字符串:", "%s…（共 %d 字符 / %d 个参数）"
          % (url.split("?", 1)[1][:76], len(url), url.count("=")))
    if args.verbose:
        print("\n完整 URL：\n" + url)
    print("=" * 78)

    # 落盘本次构造的请求（不含 cookie），便于在浏览器里做同源对照
    dump = Path(__file__).resolve().parent / "output" / "last_request.json"
    dump.parent.mkdir(exist_ok=True)
    dump.write_text(json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("请求快照已写入 %s", dump)

    if args.dry_run:
        print("\n[dry-run] 未发送请求。去掉 --dry-run（即 `python main.py`）就会真正请求。")
        await signer.close()
        return 0

    masked = mobile[:3] + "****" + mobile[-2:] if len(mobile) >= 6 else mobile
    logger.info("向 %s 发送验证码请求…", masked)
    async with session.post(url, data=body, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=25),
                            ssl=_ssl_arg(verify)) as response:
        text = await response.text()
        status = response.status
        ctype = response.headers.get("content-type")
        guard_headers = {k: v for k, v in response.headers.items()
                         if k.lower().startswith(("bd-ticket", "x-ms-token", "secure-session", "x-vc-"))}

    print("\n" + "-" * 78)
    print("HTTP 状态码 :", status)
    print("Content-Type:", ctype)
    if guard_headers:
        print("风控/票据响应头 :")
        for key, value in guard_headers.items():
            print("   %-42s %s" % (key, value[:110]))
    print("-" * 78)
    try:
        parsed = json.loads(text)
        print(json.dumps(parsed, ensure_ascii=False, indent=2)[:4000])
    except ValueError:
        parsed = None
        print(text[:2000])
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "status": status, "content_type": ctype, "headers": guard_headers,
            "json": parsed, **({"text": text[:4000]} if parsed is None else {}),
        }, ensure_ascii=False), encoding="utf-8")
    print("-" * 78)

    await signer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
