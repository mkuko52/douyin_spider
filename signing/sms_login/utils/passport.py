"""passport.py —— 抖音 Web `/passport/web/*` 接口的参数层（纯 Python 部分）。

本文件负责 `POST https://login.douyin.com/passport/web/sms_login/` 里**不需要 JS 运行时**
的全部参数；`a_bogus` 由 `utils/signer.py`（pyexecjs2 → node/mod.js）生成。

逆向来源与验证：见项目根 `分析报告.md`。核心结论：

1. `enc(s) = hex(utf8(s) XOR 0x05)`  —— mobile / code / qs / account_sdk_source_info 都用它
2. `sign = sha256( params 排序后前 10 个 "k=v"& 拼接
                   + "&" + body 排序后全部 "k=v"& 拼接
                   + "&app_key=" + APP_KEY )`
   `qs   = enc( params 排序后前 10 个的键名 , 逗号连接 )`
3. `x-tt-passport-aid-sign`：
   `PRK = HMAC-SHA256(key=ts, data=appKey)`；`OKM = HKDF-Expand(PRK, info="", L=32)`；
   `sign = hex(HMAC-SHA256(key=OKM, data="aid=6383&path=<path>&ts=<ts>"))`
   `ts` = 当天 12:00 UTC 的秒级时间戳（整天不变）

固定向量（`tests/test_vectors.py`）用的是 2026-09-18 浏览器现场抓包的真实 sms_login 请求，
`sign` / `qs` 与浏览器**逐位一致**。

注意 `service` 的编码：body 里的 JS 字符串是**原文** `https://www.douyin.com`，
由表单序列化时编码一次（线上是 `https%3A%2F%2Fwww.douyin.com`）。
不要在这里再 `quote()` 一次，否则会变成双重编码。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
from datetime import datetime, timezone
from urllib.parse import quote

APP_KEY = "163e7ce78d58971a41f5b969996d85c2"
AID = "6383"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

LOGIN_HOST = "https://login.douyin.com"
HOME = "https://www.douyin.com/"

PATH_SMS_LOGIN = "/passport/web/sms_login/"
PATH_SEND_CODE = "/passport/web/send_code/"
PATH_USER_LOGIN = "/passport/web/user/login/"
PATH_GET_QRCODE = "/passport/web/get_qrcode/"

SMS_LOGIN_URL = LOGIN_HOST + PATH_SMS_LOGIN

# 浏览器现场抓包（2026-09-18）里的 account_sdk_source_info：
# 它是「环境描述 JSON」经 enc() 后的 hex，属于半固定参数（换机器/换指纹才变）。
# 这里直接用浏览器的值，保证与浏览器环境描述一致。
ASI_BROWSER = (
    "7e276d64776172647760466a6b66707777606b667c273f3731292772606761776c736077273f6364"
    "6976602927666d776a686061776c736077273f63646976602927766d60696961776c736077273f63"
    "646976602927756970626c6b76273f3029276c6b6b60774d606c626d71273f3c3d3029276c6b6b60"
    "77526c61716d273f343c353129276a707160774d606c626d71273f373d29276a70716077526c6171"
    "6d273f34333529277260676269273f7e2773606b616a77273f27426a6a626960254c6b662b252d4b"
    "534c414c442c27292777606b6160776077273f27444b424940252d4b534c414c4429254b534c414c"
    "44254260436a7766602557515d253135333525516c252d357d35353535373d35362c25416c776066"
    "71364134342573765a305a352575765a305a35292541364134342c277829276470716a6864716c6a"
    "6b273f7e2776273f27353535353535353527292766273f273535353427292775273f273535353535"
    "35352729277634273f2735353535353535352729276634273f27353535352729277534273f273527"
    "782927756077636a7768646b6660273f7e27716c68604a776c626c6b273f34323d3c323135373032"
    "3037352b312927707660614f564d606475566c7f60273f31353c33343c35353129276b64736c6264"
    "716c6a6b516c686c6b62273f7e276160666a616061476a617c566c7f60273f3c3c33343431292760"
    "6b71777c517c7560273f276b64736c6264716c6a6b2729276c6b6c716c64716a77517c7560273f27"
    "6b64736c6264716c6a6b2729276b646860273f276d717175763f2a2a7272722b616a707c6c6b2b66"
    "6a682a27292777606b61607747696a666e6c6b62567164717076273f276b6a6b2867696a666e6c6b"
    "62272927766077736077516c686c6b62273f2766616b286664666d602960616260296a776c626c6b"
    "296c6b6b60772971715a646272272927627069605671647771273f343536322b323c3c3c3c3c3c3c"
    "3235343c3d29276270696041707764716c6a6b273f276b6a6b60277878292767776a72766077273f"
    "7e2771273f27323d313333373531323c3d3234272927676c715a75776a716a666a69273f27636469"
    "7660272927676c715a6d6069756077273f63646976607878"
)

# 抓包里的 fp（cookie s_v_web_id）。仅当会话里拿不到时兜底。
FP_FALLBACK = "verify_mu6s5arn_PTYVG3gm_p5Iw_4kOY_A19L_v1PjlXhFKtUF"


# --------------------------------------------------------------------- 基础
def enc(text: str) -> str:
    """抖音那套 enc：每个字节 XOR 0x05 再 hex。"""
    return bytes(b ^ 0x05 for b in text.encode("utf-8")).hex()


def dec(hex_text: str) -> str:
    """enc 的逆（核对抓包时用）。"""
    return bytes(b ^ 0x05 for b in bytes.fromhex(hex_text)).decode("utf-8", "ignore")


def _kv(items) -> str:
    return "&".join("%s=%s" % (k, v) for k, v in items)


# --------------------------------------------------------------------- 签名
def sort_keys(params: dict, limit: int | None = 10) -> list[str]:
    keys = sorted(params.keys())
    return keys[:limit] if limit is not None else keys


def build_sign(params: dict, body: dict) -> dict:
    """算出要拼进 query 的 sign 和 qs（params 里不要带 sign/qs/msToken/a_bogus）。"""
    keys = sort_keys(params, 10)
    i = _kv([(k, params[k]) for k in keys])
    a = _kv([(k, body[k]) for k in sorted(body)])
    s = "%s&%s&app_key=%s" % (i, a, APP_KEY)
    return {"sign": hashlib.sha256(s.encode()).hexdigest(), "qs": enc(",".join(keys))}


def hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    out = b""
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def day_ts(now: datetime | None = None) -> str:
    """当天 12:00 UTC 的秒级时间戳（sign 的 ts 参数与 aid-sign 共用，整天不变）。"""
    now = now or datetime.now(timezone.utc)
    noon = datetime(now.year, now.month, now.day, 12, 0, 0, tzinfo=timezone.utc)
    return str(int(noon.timestamp()))


def aid_sign(path: str, ts: str | None = None, aid: str = AID,
             app_key: str = APP_KEY) -> str:
    """x-tt-passport-aid-sign。"""
    ts = ts or day_ts()
    prk = hmac.new(ts.encode(), app_key.encode(), hashlib.sha256).digest()
    okm = hkdf_expand(prk, b"", 32)
    msg = ("aid=%s&path=%s&ts=%s" % (aid, path, ts)).encode()
    return hmac.new(okm, msg, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------- 参数集
def request_host_js() -> str:
    """sign 里 `request_host` 的 JS 取值（单重编码）；线上再编码一次成 %253A…

    抓包值是 `https%3A%2F%2Fwww.douyin.com` —— **不带尾斜杠**。
    """
    return quote("https://www.douyin.com", safe="")


def common_params(fp: str, asi: str | None = None, ts: str | None = None,
                  now_ms: int | None = None, p_no: str | None = None,
                  biz_trace_id: str | None = None) -> dict:
    """sms_login 的全部非签名字段（顺序与浏览器抓包一致）。

    `sign` 只吃「排序后前 10 个」，命中集合见 `tests/test_vectors.py`。
    """
    return {
        "passport_jssdk_version": "3.4.4",
        "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": 1,
        "aid": int(AID),
        "language": "zh",
        "account_app_language": "zh-CN",
        "ts": ts or day_ts(),
        "is_from_iesaccountsaas": 1,
        "p_ui": "2.4.4",
        "p_ca": "4.0.26",
        "p_ca_real": "1.0.0.910",
        "fp": fp,
        "verifyFp": fp,
        "account_sdk_source": "web",
        "account_sdk_source_info": asi or ASI_BROWSER,
        "p_js_v": "3.4.4",
        "p_js_t": "pro",
        "p_zt": "3.3.25",
        "p_ver": "1.1.3",
        "p_ver_real": "0",
        "request_host": request_host_js(),
        "p_bd": "1.0.1.19-fix.01",
        # 每次请求都变的动态参数
        "p_ts": now_ms or int(time.time() * 1000),
        "p_no": p_no or ("%064x" % random.getrandbits(256)),
        "biz_trace_id": biz_trace_id or ("%08x" % random.getrandbits(32)),
        "device_platform": "web_app",
    }


# --------------------------------------------------------------------- body
def normalize_mobile(mobile: str) -> str:
    """浏览器 body 里的 mobile JS 取值形如 `+86 13800000000`（+86 后一个空格）。"""
    digits = "".join(ch for ch in mobile if ch.isdigit())
    if digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    return "+86 " + digits


def body_sms_login(mobile: str, code: str) -> dict:
    """短信验证码登录 body —— JS 取值（明文 service，enc 过的 mobile/code）。"""
    return {
        "service": "https://www.douyin.com",
        "mix_mode": "1",
        "mobile": enc(normalize_mobile(mobile)),
        "code": enc(code),
        "fixed_mix_mode": "1",
    }


# --------------------------------------------------------------------- 工具
def serialize_query(params: dict) -> str:
    """按 dict 插入顺序拼 query，并对值做一次 URL 编码（与 requests 行为一致）。"""
    return "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())


def serialize_body(body_items) -> str:
    return "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in body_items)


def source_info(payload: dict) -> str:
    """把环境描述 JSON enc 成 account_sdk_source_info（换环境时用）。"""
    return enc(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":   # 自检：对抓包向量核 sign / aid-sign
    expected_sign = "560cf894ed29636bb0a2126071633307c8f3cdef77bb7c94e4ae0d3e00359051"
    params = {
        "passport_jssdk_version": "3.4.4", "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": 1, "aid": 6383, "language": "zh",
        "account_app_language": "zh-CN", "ts": "1789732800", "is_from_iesaccountsaas": 1,
        "p_ui": "2.4.4", "p_ca": "4.0.26", "p_ca_real": "1.0.0.910",
        "fp": FP_FALLBACK, "verifyFp": FP_FALLBACK, "account_sdk_source": "web",
        "account_sdk_source_info": ASI_BROWSER, "p_js_v": "3.4.4", "p_js_t": "pro",
        "p_zt": "3.3.25", "p_ver": "1.1.3", "p_ver_real": "0",
        "request_host": request_host_js(), "p_bd": "1.0.1.19-fix.01",
        "p_ts": 1789740278617,
        "p_no": "ee2d3166745dac64e03e1b00d62e78ed51b7ee09a1e00a9f10ebde487e4ff69c",
        "biz_trace_id": "093fee5c", "device_platform": "web_app",
    }
    body = body_sms_login("13800000000", "123456")
    got = build_sign(params, body)
    print("sign :", got["sign"])
    print("一致 :", got["sign"] == expected_sign)
    print("mobile body:", body["mobile"], "(抓包: 2e3d332534363d3535353535353535)")
    print("aid-sign:", aid_sign(PATH_SMS_LOGIN, ts="1789732800"))
    print("aid 一致:", aid_sign(PATH_SMS_LOGIN, ts="1789732800")
          == "b4e618e23220e5d02d91c1b546f4e1481d117980bb8d7101892da0a96dce8cdc")
