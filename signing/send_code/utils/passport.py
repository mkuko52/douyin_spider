"""passport.py —— 抖音 Web 登录接口的"纯协议"参数层（逆向成果落地）。

已完全逆出并验证的部分：

1. 编码 enc(s) = hex(utf8(s) XOR 0x05)
   —— account / password / mobile / code / type / qs / account_sdk_source_info 都用它

2. 签名（模块 86465 的 `d` 函数）
   sign = sha256( params 排序后前 10 个的 "k=v"& 拼接
                  + "&" + body 排序后全部 "k=v"& 拼接
                  + "&app_key=" + APP_KEY )
   qs   = enc( params 排序后前 10 个的键名, 逗号连接 )

3. x-tt-passport-aid-sign（模块 370824）
   PRK  = HMAC-SHA256(key=ts, data=appKey)
   OKM  = HKDF-Expand(PRK, info="", L=32)
   sign = hex(HMAC-SHA256(key=OKM, data="aid=6383&path=<url路径>&ts=<ts>"))
   ts   = 当天 12:00 UTC 的秒级时间戳（同一天内固定）
   —— 已用抓包真实值验证：/passport/web/user/login/ 与浏览器完全一致

还没做（见 js_reverse_cache/env/passport_login_sign.md 第 10 节）：
   - bd_ticket_guard（EC P-256 + CSR + ECDH + HKDF）
   - x-tt-session-dtrait（RSA 加密设备信号）
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import quote

APP_KEY = "163e7ce78d58971a41f5b969996d85c2"
AID = "6383"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

LOGIN_HOST = "https://login.douyin.com"
PATH_SEND_CODE = "/passport/web/send_code/"
PATH_SMS_LOGIN = "/passport/web/sms_login/"
PATH_USER_LOGIN = "/passport/web/user/login/"
PATH_GET_QRCODE = "/passport/web/get_qrcode/"


# --------------------------------------------------------------------- 基础
def enc(text: str) -> str:
    """抖音那套 enc：每个字节 XOR 0x05 再 hex。"""
    return bytes(b ^ 0x05 for b in text.encode("utf-8")).hex()


def dec(hex_text: str) -> str:
    """enc 的逆（抓包核对时用）。"""
    raw = bytes.fromhex(hex_text)
    return bytes(b ^ 0x05 for b in raw).decode("utf-8", "ignore")


def _kv(items) -> str:
    return "&".join("%s=%s" % (k, v) for k, v in items)


# --------------------------------------------------------------------- 签名
def build_sign(params: dict, body: dict) -> dict:
    """算出要拼进 query 的 sign 和 qs。"""
    keys = sorted(params.keys())[:10]
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
    """当天 12:00 UTC 的秒级时间戳（aid-sign 和 params.ts 都用它）。"""
    now = now or datetime.now(timezone.utc)
    noon = datetime(now.year, now.month, now.day, 12, 0, 0, tzinfo=timezone.utc)
    return str(int(noon.timestamp()))


def aid_sign(path: str, ts: str | None = None, aid: str = AID, app_key: str = APP_KEY) -> str:
    """x-tt-passport-aid-sign。"""
    ts = ts or day_ts()
    prk = hmac.new(ts.encode(), app_key.encode(), hashlib.sha256).digest()
    okm = hkdf_expand(prk, b"", 32)
    msg = ("aid=%s&path=%s&ts=%s" % (aid, path, ts)).encode()
    return hmac.new(okm, msg, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------- 参数集
def source_info(browser: dict | None = None) -> str:
    """account_sdk_source_info：浏览器环境 JSON，加密后作为参数传。"""
    import json
    info = browser or {
        "hardwareConcurrency": 8,
        "webdriver": False,
        "chromedriver": False,
        "chelldriver": False,
        "plugins": 5,
        "innerHeight": 911,
        "innerWidth": 1920,
        "outerHeight": 1032,
        "outerWidth": 1920,
        "webgl": {"vendor": "Google Inc. (Intel)",
                  "renderer": "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        "automation": {"s": "00000000", "c": "0000", "p": "0000000",
                       "s1": "00000000", "c1": "0000", "p1": "0"},
        "performance": {"timeOrigin": time.time() * 1000, "usedJSHeapSize": 30000000,
                        "navigationTiming": {"decodedBodySize": 800000, "entryType": "navigation",
                                             "initiatorType": "navigation",
                                             "name": "https://www.douyin.com/",
                                             "renderBlockingStatus": "non-blocking"}},
        "browser": {"t": "%013d" % int(time.time() * 1000), "bit_protocol": "false",
                    "bit_helper": False},
    }
    return enc(json.dumps(info, separators=(",", ":")))


def common_params(fp: str, now_ms: int | None = None) -> dict:
    """除 sign/qs 之外的公共参数（顺序/取值按抓包对齐）。"""
    import random
    return {
        "passport_jssdk_version": "3.4.4",
        "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": 1,
        "aid": int(AID),
        "language": "zh",
        "account_app_language": "zh-CN",
        "ts": day_ts(),
        "is_from_iesaccountsaas": 1,
        "p_ui": "2.4.4",
        "p_ca": "4.0.26",
        "p_ca_real": "1.0.0.910",
        "fp": fp,
        "verifyFp": fp,
        "account_sdk_source": "web",
        "account_sdk_source_info": source_info(),
        "p_js_v": "3.4.4",
        "p_js_t": "pro",
        "p_zt": "3.3.25",
        "p_ver": "1.1.3",
        "p_ver_real": "0",
        "request_host": quote("https://www.douyin.com", safe=""),
        "p_bd": "1.0.1.19-fix.01",
        "p_ts": now_ms or int(time.time() * 1000),
        "p_no": "%064x" % random.getrandbits(256),
        "biz_trace_id": "%08x" % random.getrandbits(32),
        "device_platform": "web_app",
    }


# --------------------------------------------------------------------- body
def body_send_code(mobile: str) -> dict:
    """发短信验证码的 body（抓包：type=enc("24")）。"""
    return {"is6Digits": "1", "mix_mode": "1", "mobile": enc(mobile), "type": enc("24"),
            "fixed_mix_mode": "1"}


def body_sms_login(mobile: str, code: str) -> dict:
    """短信验证码登录的 body。"""
    return {"service": quote("https://www.douyin.com", safe=""), "mix_mode": "1",
            "mobile": enc(mobile), "code": enc(code), "fixed_mix_mode": "1"}


def body_user_login(account: str, password: str) -> dict:
    """账号密码登录的 body。"""
    return {"need_check_base_info": "true", "service": "https://www.douyin.com",
            "account_type": "0", "mix_mode": "1", "account": enc(account),
            "password": enc(password), "fixed_mix_mode": "1"}


if __name__ == "__main__":   # 自检：对着抓包向量比对
    v = aid_sign(PATH_USER_LOGIN, ts="1789646400")
    expect = "f47c4485d8ae2ce694dd5ea5e182c8c1d2c0051ae04fbe60613bf00e90d920e9"
    print("aid-sign( user/login ) =", v)
    print("与抓包一致:", v == expect)
    print("enc 校对: +86 13800000000 ->", enc("+86 13800000000"),
          "(期望: 2e3d332534363d3535353535353535)")
    print("enc 校对: 24 ->", enc("24"), "(抓包: 3731)")
    print("dec 校对: 637263 ->", dec("637263"))
