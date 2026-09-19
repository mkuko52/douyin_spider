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

PATH = "/aweme/v1/web/user/profile/other/"


def test_url():
    params = C.build_params(sec_user_id="MS4wLjABAAAApBXenoFyCKJlEi9DItxR21JPOlhmiGbMiRGugv4aPbZxc6615SAQ7kctt1Lhq_Qa")
    parsed = urlparse(C.build_url(PATH, params))
    assert parsed.scheme == "https" and parsed.netloc == "www.douyin.com", parsed
    assert parsed.path == PATH, parsed.path
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert query["aid"] == ["6383"] and query["device_platform"] == ["webapp"], query
    assert query["sec_user_id"] == ["MS4wLjABAAAApBXenoFyCKJlEi9DItxR21JPOlhmiGbMiRGugv4aPbZxc6615SAQ7kctt1Lhq_Qa"], query
    print("test_url OK")


def main() -> int:
    test_url()
    print("\n1/1 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
