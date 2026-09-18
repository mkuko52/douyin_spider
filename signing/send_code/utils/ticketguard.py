"""ticketguard.py —— 把抖音的 `bd_ticket_guard` 用纯 Python 复现。

为什么要它：`user/login`、`sms_login`、`send_code`、`check_qrconnect` 这几个接口
在 SDK 里属于 `bd_ticket_guard` 保护名单（`signVersion: 2`）。只把参数/签名对齐是不够的，
实测纯 Python 一律 `2156 系统繁忙` —— 缺的就是这一层。

流程（逆向自 `async/85271.cbba7deb.js`）：
  1. 生成 EC **P-256** 密钥对
  2. 调 `get_client_cert` 拿服务端证书（里面有服务端公钥，用于 ECDH）
  3. 把自己公钥的**未压缩点**（0x04||X||Y，65 字节）base64 后放进
     `bd_ticket_guard_client_data` cookie（整段再 base64 一次）
  4. 之后请求带上这个 cookie（+相关头）

编码对照（从真实 cookie 解出来的真值）：
  cookie 原文 = base64({
      "bd-ticket-guard-version": 2,
      "bd-ticket-guard-iteration-version": 1,
      "bd-ticket-guard-ree-public-key": base64(未压缩EC点),
      "bd-ticket-guard-web-version": 2 })
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

AID = 6383
GET_CLIENT_CERT = "https://login.douyin.com/passport/ticket_guard/get_client_cert/"
COOKIE_NAME = "bd_ticket_guard_client_data"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@dataclass
class TicketGuard:
    """一次会话的 ticket_guard 材料。"""

    private_key: ec.EllipticCurvePrivateKey
    public_point: bytes          # 0x04 || X || Y
    cookie_value: str            # 放进 cookie 的字符串

    @property
    def ree_public_key_b64(self) -> str:
        return _b64(self.public_point)

    def headers(self) -> dict:
        """该会话给每个请求带的头（目前主要是这个 client-data）。"""
        return {
            "bd-ticket-guard-client-data": self.cookie_value,
            "bd-ticket-guard-version": "2",
        }


def generate() -> TicketGuard:
    """生成密钥对并组好 cookie 值（不需要联网）。"""
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    payload = {
        "bd-ticket-guard-version": 2,
        "bd-ticket-guard-iteration-version": 1,
        "bd-ticket-guard-ree-public-key": _b64(point),
        "bd-ticket-guard-web-version": 2,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return TicketGuard(private_key=key, public_point=point, cookie_value=_b64(raw))


def make_csr(guard: TicketGuard, hostname: str = "www.douyin.com") -> str:
    """生成 CSR（SHA256withECDSA，subject /C=CN/CN=bd_ticket_guard，带 SAN）。

    有些场景（initType=cert）要提交 CSR 换客户端证书；pubKey 模式用不到，先备着。
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.COMMON_NAME, "bd_ticket_guard"),
        ]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(guard.private_key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def fetch_server_cert(session) -> dict:
    """第②步：get_client_cert 握手（返回 server_cert / server_data）。

    注意 body 用逗号连接（`server_data=1,aid=6383`），跟普通表单不一样。
    """
    resp = session.post(
        GET_CLIENT_CERT + "?aid=%d&is_from_ttaccountsdk=1" % AID,
        data="server_data=1,aid=%d" % AID,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Origin": "https://www.douyin.com",
            "Referer": "https://www.douyin.com/",
        },
        timeout=25,
    )
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:400]}


def ecdh_shared_secret(guard: TicketGuard, server_cert_pem: str) -> bytes:
    """和服务端证书里的公钥做 ECDH（P-256），再走 HKDF 展开成 32 字节。

    对应 JS 的：deriveBits(ECDH) → D(b"", shared, b"", 32)
    """
    import hashlib
    import hmac

    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    cert = x509.load_pem_x509_certificate(server_cert_pem.encode())
    peer = cert.public_key()
    if not isinstance(peer, _ec.EllipticCurvePublicKey):
        raise ValueError("服务端证书里不是 EC 公钥")
    shared = guard.private_key.exchange(_ec.ECDH(), peer)

    # HKDF-Expand(PRK = HMAC(key=32个0, data=shared), info="", L=32)
    prk = hmac.new(b"\x00" * 32, shared, hashlib.sha256).digest()
    out = b""
    block = b""
    counter = 1
    while len(out) < 32:
        block = hmac.new(prk, block + b"" + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:32]


if __name__ == "__main__":
    g = generate()
    print("ree-public-key(b64) len:", len(g.ree_public_key_b64))
    print("未压缩点 len:", len(g.public_point), "head:", g.public_point[:1].hex())
    print("cookie 值 len:", len(g.cookie_value))
    decoded = json.loads(base64.b64decode(g.cookie_value).decode())
    print("cookie 解码:", decoded)
    print("CSR 头一行:", make_csr(g).splitlines()[0])
