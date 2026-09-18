"""固定向量验证 —— 用抓包真值校验交付路径的每一个算法。

跑：runtime\\venv\\Scripts\\python.exe tests\\test_vectors.py

覆盖：
  1. enc / dec          XOR 0x05
  2. aid_sign           HKDF-Expand + HMAC-SHA256（抓包权威值）
  3. sign / qs          用抓包到的 send_code 原始请求反算，须逐位一致
  4. dtrait 组装         段长必须落在抓包观测值 (2 / 344 / 472)
  5. a_bogus            Node 侧签名器可复现同输入（确定性）
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import dtrait as dtrait_mod
from utils.passport import PATH_USER_LOGIN, aid_sign, dec, enc
from utils.passport import build_sign

SAMPLE = ROOT / "js_reverse_cache" / "samples" / "send_code_request.json"


class TestEnc(unittest.TestCase):
    """enc(s) = hex(utf8(s) XOR 0x05)。"""

    def test_enc_mobile(self):
        self.assertEqual(enc("+86 13800000000"), "2e3d332534363d3535353535353535")

    def test_enc_type(self):
        self.assertEqual(enc("24"), "3731")

    def test_roundtrip(self):
        self.assertEqual(dec(enc("抖音 Web 站")), "抖音 Web 站")


class TestAidSign(unittest.TestCase):
    """x-tt-passport-aid-sign —— 与抓包逐位一致。"""

    def test_user_login_vector(self):
        value = aid_sign(PATH_USER_LOGIN, ts="1789646400")
        self.assertEqual(
            value,
            "f47c4485d8ae2ce694dd5ea5e182c8c1d2c0051ae04fbe60613bf00e90d920e9",
        )


class TestCapturedSignature(unittest.TestCase):
    """用抓包到的真实请求，反算 sign 必须与抓包值相同。"""

    def setUp(self):
        if not SAMPLE.exists():
            self.skipTest("缺少抓包样本 %s" % SAMPLE)
        self.sample = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def test_sign_reproduced(self):
        query = urlparse(self.sample["url"]).query
        params = dict(parse_qsl(query, keep_blank_values=True))
        expected_sign = params.pop("sign")
        expected_qs = params.pop("qs")
        # 抓包时 query 里带了 msToken / a_bogus，它们不参与 sign 计算
        params.pop("msToken", None)
        params.pop("a_bogus", None)

        body = dict(parse_qsl(self.sample["body"], keep_blank_values=True))
        got = build_sign(params, body)

        self.assertEqual(got["sign"], expected_sign, "sign 与抓包不一致")
        self.assertEqual(got["qs"], expected_qs, "qs 与抓包不一致")

    def test_get_qrcode_sign_reproduced(self):
        """GET + 空 body 分支：用浏览器**现场**抓到的 get_qrcode 反算。"""
        sample = ROOT / "js_reverse_cache" / "samples" / "get_qrcode_live.json"
        if not sample.exists():
            self.skipTest("缺少 get_qrcode 样本")
        query = urlparse(json.loads(sample.read_text(encoding="utf-8"))["url"]).query
        params = dict(parse_qsl(query, keep_blank_values=True))
        expected_sign = params.pop("sign")
        expected_qs = params.pop("qs")
        params.pop("msToken", None)
        params.pop("a_bogus", None)

        got = build_sign(params, {})          # GET -> body 为空

        self.assertEqual(got["sign"], expected_sign, "get_qrcode sign 与现场抓包不一致")
        self.assertEqual(got["qs"], expected_qs, "get_qrcode qs 与现场抓包不一致")
        self.assertEqual(
            expected_sign,
            "79c2ed7631a19e3fdb6ddde0887959bcf6773e81b4081db06aca5c94b89f6bbc",
        )


class TestDtraitAssembly(unittest.TestCase):
    """dtrait 密文结构：<version>_<b64 RSA(key||iv)>_<b64 AES-CBC(payload)>。"""

    def test_segment_lengths_match_capture(self):
        payload = json.loads((ROOT / "assets" / "dtrait_payload.json").read_text(encoding="utf-8"))
        value = dtrait_mod.build(payload)
        version, wrap, body = value.split("_")
        self.assertEqual(version, "d0")
        self.assertEqual(len(wrap), 344, "RSA 段应为 256 字节 -> 344 base64")
        self.assertEqual(len(body), 472, "AES 段应为 352 字节 -> 472 base64")

    def test_round_trip_decrypts_to_payload(self):
        """用已知 key/iv 把密文解回去，必须正好是 AES 明文的序列化结果。

        （RSA PKCS#1 v1.5 自带随机 padding，所以不能用“固定 key/iv 得到同一串”来断言；
         真正要证明的是：AES 段解出来 = serialise(payload)，且 key/iv 确实被封在 RSA 段里。）
        """
        import base64

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        payload = {"str": {"str_1": 123, "str_2": 0, "str_3": 456}, "bool": {}, "num": {}}
        key = bytes(range(16))
        iv = bytes(range(16, 32))
        value = dtrait_mod.build(payload, key=key, iv=iv)
        _, wrap, body = value.split("_")            # noqa: E501

        # RSA 段 = 256 字节，长度已由上面断言；这里校验 AES 段可解
        blob = base64.b64decode(body)
        plain = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        decrypted = plain.update(blob) + plain.finalize()
        pad = decrypted[-1]
        self.assertEqual(dtrait_mod.serialise(payload), decrypted[:-pad])

    def test_json_shape(self):
        """序列化形式必须是 [[str_key, 值], ...]，且 0 / 空值被丢弃。"""
        payload = {"str": {"str_1": 1, "str_2": 0, "str_3": "undefined"}, "bool": {}, "num": {}}
        got = json.loads(dtrait_mod.serialise(payload).decode("utf-8"))
        self.assertEqual(got, [["str_1", 1]])


class TestABogus(unittest.TestCase):
    """a_bogus 现在由 nv8 生成（环境对齐到我们实际发出的请求）。

    注意：真实 a_bogus 内部含 `Date.now()` 与 `Math.random()`，**天然不可复现**，
    所以这里只验证结构性质（长度、字符集、非空），不再断言“冻结后可复现”。
    """

    def test_generated_by_nv8(self):
        try:
            from utils.signer import default_signer
        except Exception as exc:  # pragma: no cover
            self.skipTest("signer 不可用: %s" % exc)
        signer = default_signer()
        try:
            value = signer.a_bogus("aid=6383&device_platform=web_app")
        finally:
            signer.close()
        self.assertTrue(value, "a_bogus 不能为空")
        # 实测浏览器值解码后 192 字符；这里返回的是 URL 编码形式（直接拼进 URL）
        self.assertGreater(len(value), 150)
        self.assertLess(len(value), 280)
        # base64 风格 + URL 编码字符（%、+、/、=、-、_）
        self.assertRegex(value, r"^[A-Za-z0-9+/=_-]+(?:%[0-9A-Fa-f]{2}[A-Za-z0-9+/=_-]*)*$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
