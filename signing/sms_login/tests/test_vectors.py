"""test_vectors.py —— sms_login 参数层的固定向量验证（离线，不发网络）。

向量来源：2026-09-18 浏览器现场抓包的真实 sms_login 请求
（`js_reverse_cache/samples/sms_login_browser_vector.json`）。

跑法：
    python tests/test_vectors.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import passport as P                     # noqa: E402
from utils.signer import a_bogus                    # noqa: E402

VECTOR = json.loads((ROOT / "js_reverse_cache" / "samples"
                     / "sms_login_browser_vector.json").read_text(encoding="utf-8"))


class TestEnc(unittest.TestCase):
    def test_enc_dec_roundtrip(self):
        for text in ("+86 13800000000", "24", "123456", "aA1-_=/+"):
            self.assertEqual(P.dec(P.enc(text)), text)

    def test_captured_values(self):
        self.assertEqual(P.enc("+86 13800000000"), "2e3d332534363d3535353535353535")
        self.assertEqual(P.enc("24"), "3731")
        self.assertEqual(P.enc("123456"), "343736313033")


class TestSignature(unittest.TestCase):
    """sign / qs 必须与浏览器抓包逐位一致。"""

    def test_captured_sign_and_qs(self):
        params = dict(VECTOR["params"])
        body = P.body_sms_login("13800000000", "123456")
        got = P.build_sign(params, body)
        self.assertEqual(got["sign"], VECTOR["expected"]["sign"])
        self.assertEqual(got["qs"], VECTOR["expected"]["qs"])

    def test_sign_key_set(self):
        self.assertEqual(P.sort_keys(VECTOR["params"], 10), VECTOR["expected"]["signKeys"])

    def test_body_matches_wire(self):
        body = P.body_sms_login("13800000000", "123456")
        self.assertEqual(body["service"], "https://www.douyin.com")   # JS 取值是原文
        self.assertEqual(body["mobile"], VECTOR["bodyRaw"]["mobile"])
        self.assertEqual(body["code"], VECTOR["bodyRaw"]["code"])
        for key, value in VECTOR["bodyRaw"].items():
            if key != "service":
                self.assertEqual(body[key], value)

    def test_request_host_is_single_encoded_value(self):
        # sign 里是 `https%3A%2F%2Fwww.douyin.com`（线上再编码一次成 %253A…）
        self.assertEqual(P.request_host_js(), VECTOR["params"]["request_host"])


class TestAidSign(unittest.TestCase):
    def test_captured_aid_sign(self):
        got = P.aid_sign(VECTOR["path"], ts=VECTOR["expected"]["aidSignTs"])
        self.assertEqual(got, VECTOR["expected"]["aidSign"])

    def test_day_ts_is_stable_within_day(self):
        from datetime import datetime, timezone
        a = P.day_ts(datetime(2026, 9, 18, 1, 0, tzinfo=timezone.utc))
        b = P.day_ts(datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(a, b)
        self.assertEqual(a, VECTOR["expected"]["aidSignTs"])


class TestABogus(unittest.TestCase):
    """a_bogus 由 Node（pyexecjs2）生成：形态 + 可复现性。"""

    def test_shape_and_reproducibility(self):
        frozen = {"freeze": VECTOR["aBogus"]["freeze"]}
        query = VECTOR["aBogus"]["freezeQuery"]
        v1 = a_bogus(query, frozen)
        v2 = a_bogus(query, frozen)
        self.assertEqual(v1, v2, "同输入 + 同 freeze 必须逐位可复现")
        self.assertEqual(len(v1), VECTOR["aBogus"]["freezeExpectedLen"])
        self.assertRegex(v1, r"^[A-Za-z0-9+/=_-]+$")

    def test_different_input_differs(self):
        frozen = {"freeze": VECTOR["aBogus"]["freeze"]}
        self.assertNotEqual(a_bogus("a=1&b=2", frozen), a_bogus("a=1&b=3", frozen))


if __name__ == "__main__":
    unittest.main(verbosity=2)
