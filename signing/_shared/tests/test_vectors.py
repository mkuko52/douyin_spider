"""tests/test_vectors.py —— `_shared` 的离线固定向量（不发网络）。

覆盖：
1. `params.build_url`（路径 + 公共参数 + 业务参数）
2. `signer.a_bogus` 在冻结环境下**字节确定**（6 个数据接口各一条查询）
3. `signer.sign_url` 追加 a_bogus 且保留原有参数

运行：`python _shared/tests/test_vectors.py`（或从 `_shared/` 目录 `python tests/test_vectors.py`）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]          # signing/
sys.path.insert(0, str(ROOT))

from _shared import params as C                     # noqa: E402
from _shared import http                            # noqa: E402
from _shared.signer import a_bogus, sign_url        # noqa: E402

FREEZE = {"freeze": {"now": 1757000000000, "seed": 20260917}}
SEC_UID = "MS4wLjABAAAApBXenoFyCKJlEi9DItxR21JPOlhmiGbMiRGugv4aPbZxc6615SAQ7kctt1Lhq_Qa"
AWEME = "7626316866109066511"

# 每条 = (接口用途, 用于签名的 query, 冻结后的 a_bogus 固定取值)
VECTORS = [
    ("aweme_detail",
     f"device_platform=webapp&aid=6383&aweme_id={AWEME}",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSykei/Wo-PHxTCc70GkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uS6f="),
    ("comment_list",
     f"device_platform=webapp&aid=6383&aweme_id={AWEME}&cursor=0&count=20",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSyBli/bjaPHxuRc70TkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uSAD="),
    ("comment_reply",
     "device_platform=webapp&aid=6383&item_id=7626316866109066511&comment_id=7627000000000000000",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSymli/R9pPHOunc70YkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uS5L="),
    ("aweme_feed",
     "device_platform=webapp&aid=6383&count=10&refresh_index=1",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSyfei/RjpPHxTVc7MbkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uSUY="),
    ("user_profile",
     f"device_platform=webapp&aid=6383&sec_user_id={SEC_UID}",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSyDei/SLrPHOzjc7MTkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uSl6="),
    ("aweme_search",
     "device_platform=webapp&aid=6383&keyword=minecraft&offset=0&count=20",
     "Yj0fDwWixomcKdKtYCNGyaBljHnANBSy4ei/W9aPHOTWc7MTkRNvLo6tJOiR4h6iebMiiZ3HPf4OYVnPT0A12Fn"
     "kKmkkumhW4t/VVXfogqqpbMiMLqjxeu8zzw0uUS4Y8OHtxIXU1tBohDMlkqCNAoO9SA0JQ8bMPrNWDAT9rDCWp"
     "B6T9o/uSvS="),
]


def test_build_url():
    url = C.build_url("/aweme/v1/web/aweme/detail/", C.build_params(aweme_id=AWEME))
    parsed = urlparse(url)
    assert parsed.scheme == "https" and parsed.netloc == "www.douyin.com", url
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert query["aid"] == ["6383"] and query["aweme_id"] == [AWEME], query
    assert C.COMMON_PARAMS["device_platform"] == "webapp"
    print("test_build_url OK")


def test_frozen_vectors():
    for label, query, expected in VECTORS:
        value = a_bogus(query, FREEZE)
        assert value == expected, f"[{label}] a_bogus 漂移:\n{value}\n!=\n{expected}"
    print(f"test_frozen_vectors OK（{len(VECTORS)} 条）")


def test_sign_url():
    signed = sign_url(C.build_url("/aweme/v1/web/aweme/detail/", C.build_params(aweme_id=AWEME)),
                      FREEZE)
    query = parse_qs(urlparse(signed).query, keep_blank_values=True)
    assert query.get("a_bogus", [""])[0], "缺少 a_bogus"
    assert query["aweme_id"] == [AWEME], "原参数被破坏"
    print("test_sign_url OK")


def test_login_check():
    """登录判定：`status_code == 0` 才算 www 已登录（`8` = 未登录/会话过期）。"""
    assert http.is_logged_in({"status_code": 0}) is True
    assert http.is_logged_in({"status_code": 8, "status_msg": "用户未登录"}) is False
    assert http.is_logged_in({}) is False and http.is_logged_in(None) is False
    assert http.PATH_LOGIN_CHECK == "/aweme/v1/web/notice/count/"
    print("test_login_check OK")


def main() -> int:
    test_build_url()
    test_frozen_vectors()
    test_sign_url()
    test_login_check()
    print("\n4/4 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
