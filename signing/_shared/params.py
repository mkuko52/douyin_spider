"""params.py —— 抖音 Web 数据接口（/aweme/v1/web/*）的公共参数层（纯 Python）。

**唯一一份**，所有数据接口项目共用。包含：
- 固定「像浏览器」的公共查询参数（`COMMON_PARAMS`）；
- `build_params` / `build_url`。

`a_bogus` 由 `signer.py`（pyexecjs2 → `node/mod.js`）追加。
每个项目的**接口路径与业务参数**在自己的 `main.py` 里声明。

参数来源（已 live 验证）：
- 旧项目 `douyin_spider/utils/client.py`（COMMON_PARAMS）
- 新项目抓到的抖音前端源码 `signing/send_code/js_reverse_cache/source/app_client-entry_*.js`
"""

from __future__ import annotations

from urllib.parse import urlencode

BASE = "https://www.douyin.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# 网页每次请求都会带的「像浏览器」固定参数。抖音会校验，缺了容易被拦。
COMMON_PARAMS: dict[str, str] = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "update_version_code": "170400",
    "pc_client_type": "1",
    "pc_libra_divert": "Windows",
    "support_h265": "1",
    "support_dash": "1",
    "cpu_core_num": "24",
    "version_code": "170400",
    "version_name": "17.4.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "151.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "151.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "device_memory": "32",
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "150",
}


def build_params(**extra) -> dict:
    """公共参数 + 本次接口参数（None 跳过，其余转字符串）。"""
    params = dict(COMMON_PARAMS)
    for key, value in extra.items():
        if value is not None:
            params[key] = str(value)
    return params


def build_url(path: str, params: dict) -> str:
    """拼出未签名的 URL（`a_bogus` 由 signer 追加）。"""
    return f"{BASE}{path}?{urlencode(params)}"
