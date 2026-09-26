"""tests/test_vectors.py —— 本接口的 URL / 参数组装（不发网络）。

公共参数的 a_bogus 固定向量在 `signing/_shared/tests/test_vectors.py`（唯一一份）。

运行：`python tests/test_vectors.py`。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]          # signing/
sys.path.insert(0, str(ROOT))

from _shared import params as C                     # noqa: E402
from _shared.nv8 import web_sign                    # noqa: E402

PATH = "/aweme/v1/web/aweme/detail/"


def test_url():
    params = C.build_params(aweme_id="7626316866109066511")
    parsed = urlparse(C.build_url(PATH, params))
    assert parsed.scheme == "https" and parsed.netloc == "www.douyin.com", parsed
    assert parsed.path == PATH, parsed.path
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert query["aid"] == ["6383"] and query["device_platform"] == ["webapp"], query
    assert query["aweme_id"] == ["7626316866109066511"], query
    print("test_url OK")


def test_web_sign():
    """详情专用的 secsdk 动态签名必须在本地生成，不发网络请求。"""
    uifid = "test-uifid"
    url = C.build_url(PATH, C.build_params(aweme_id="7626316866109066511", uifid=uifid))
    signed, headers = web_sign(url, uifid)
    query = parse_qs(urlparse(signed).query)
    assert query["uifid"] == [uifid]
    assert query["timestamp"][0].isdigit()
    assert len(query["x-secsdk-web-signature"][0]) == 32
    assert headers["uifid"] == uifid
    print("test_web_sign OK")


def main() -> int:
    test_url()
    test_web_sign()
    print("\n2/2 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
