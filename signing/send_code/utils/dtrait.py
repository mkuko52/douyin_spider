"""dtrait.py —— 把设备指纹 payload 组装成请求头 `x-tt-session-dtrait`。

逆向结论（见 js_reverse_cache/env/passport_login_sign.md 第 11/15 节）：

    密文结构：  <centralVersion>_<b64(RSA-2048(AES key||iv))>_<b64(AES-128-CBC(payload))>

    - centralVersion = "d0"      （SDK 内置常量）
    - AES           ：随机 16 字节 key + 随机 16 字节 iv，AES-128-CBC + PKCS#7
    - RSA           ：PKCS#1 v1.5，用 SDK 内置的 central 公钥包 (key||iv)
    - payload       ：由 uc-secure-dtrait-core（JSVMP）现场采集，Node 侧产出

抓包对照：真实头的两段 base64 长度是 344 / 472
（344 → RSA-2048 密文 256 字节；472 → AES 密文 352 字节）。

注意：payload 必须**每次请求现场采集**。复用旧值会被服务端判废（2156）。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ASSETS = Path(__file__).resolve().parents[1] / "assets"
RSA_JSON = ASSETS / "dtrait_rsa.json"

# 组装后 AES 密文的参照长度（字节）；浏览器实测 352。
REFERENCE_CIPHER_LEN = 352


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def load_keys() -> dict:
    """读 SDK 内置的 RSA 公钥与版本前缀。"""
    data = json.loads(RSA_JSON.read_text(encoding="utf-8"))

    def _pem(value: str) -> str:
        # 文件里既有 base64(PEM) 也有 PEM 明文，两种都吃。
        if "BEGIN" in value:
            return value
        try:
            return base64.b64decode(value).decode("utf-8")
        except Exception:
            return value

    return {
        "central": serialization.load_pem_public_key(_pem(data["centralRsaPub"]).encode()),
        "edge": serialization.load_pem_public_key(_pem(data["edgeRsaPub"]).encode()),
        "centralVersion": data.get("centralVersion", "d0"),
    }


def serialise(payload: dict) -> bytes:
    """payload -> AES 明文。

    实测反推：明文是 `[[str_key, 值], ...]` 形式，长度落在浏览器观测区间
    （本地 349 → 补齐 352）。只保留「有值」的字符串属性（0 / 空 / undefined 丢掉）。
    """
    pairs = []
    for key, value in payload.get("str", {}).items():
        if value in (None, "", "0", "undefined", "''", 0):
            continue
        try:
            pairs.append([key, int(value)])
        except (TypeError, ValueError):
            pairs.append([key, value])
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _aes_cbc_encrypt(key: bytes, iv: bytes, plain: bytes) -> bytes:
    pad = 16 - (len(plain) % 16)
    plain = plain + bytes([pad]) * pad                      # PKCS#7
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(plain) + enc.finalize()


def build(payload: dict, key: bytes | None = None, iv: bytes | None = None) -> str:
    """产出一次性的 `x-tt-session-dtrait` 值。"""
    keys = load_keys()
    key = key or os.urandom(16)
    iv = iv or os.urandom(16)

    plain = serialise(payload)
    wrap = keys["central"].encrypt(key + iv, padding.PKCS1v15())
    body = _aes_cbc_encrypt(key, iv, plain)
    return "%s_%s_%s" % (keys["centralVersion"], _b64(wrap), _b64(body))


if __name__ == "__main__":   # 自检：用离线 payload 跑一遍，看段长是否落在抓包区间
    sample = json.loads((ASSETS / "dtrait_payload.json").read_text(encoding="utf-8"))
    value = build(sample)
    version, wrap, body = value.split("_")
    print("payload: str=%d bool=%d" % (len(sample.get("str", {})), len(sample.get("bool", {}))))
    print("明文长度:", len(serialise(sample)))
    print("段长:", [len(version), len(wrap), len(body)], " (抓包参考: ['d0'=2, 344, 472])")
    print("前 60 字符:", value[:60])
