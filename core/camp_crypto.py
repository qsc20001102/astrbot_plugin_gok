"""王者营地协议的加密原语：RSA(PKCS#1 v1.5) 与 encodeParam 生成。

对应参考实现的 `src/lib/camp/wechat-login.ts` 与 `src/lib/camp/camp-api.ts`：

* `specialEncodeParam` —— 用营地公钥对 `{timestamp, nonce}` 做 PKCS#1 v1.5 加密；
  1024 位密钥单块上限 117 字节，超长需分块拼接（Node 端 `rsaEncryptChunked`）。
* `encodeParam` —— 用登录返回的 `userKey` 作为密钥，对 `{timestamp, nonce}` 做 XXTEA
  加密后 base64；这是请求携带的主要安全参数。
* `encodeRes` 解码 —— 服务端用私钥按 PKCS#1 v1.5 "加密"（即 Node 的
  `crypto.publicDecrypt` 场景），客户端用公钥恢复出 userKey。
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Any

from . import xxtea

__all__ = [
    "DEFAULT_PUBLIC_KEY",
    "build_public_key_pem",
    "rsa_encrypt_chunked",
    "rsa_recover_json",
    "build_special_encode_param",
    "build_encode_param",
    "decode_encode_res",
    "now_ms",
]

# 营地客户端内置的 RSA 公钥（1024 位，PKCS#1 v1.5）。
DEFAULT_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC0h62mV/zjJtFsNdfFNlxksfUOpjDI2KCcBrPiA8T7"
    "szABT4InLDTrdXAW84QyGNiazB0i7pgPCNGSAYbiJrCRutZ5jQsVS0Wg/RnXfwVQDJcAHJDjP5IXyroe"
    "LX7NUxDai8nPcpfRsvq6sneobyPexZSH0TlVSnecsJZTj5wu/wIDAQAB"
)


def now_ms() -> int:
    """当前毫秒时间戳。"""
    return int(time.time() * 1000)


def build_public_key_pem(public_key_b64: str) -> str:
    """把纯 base64 公钥包装成 PEM。"""
    chunks = [public_key_b64[i : i + 64] for i in range(0, len(public_key_b64), 64)]
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        + "\n".join(chunks)
        + "\n-----END PUBLIC KEY-----"
    )


def _load_public_key(public_key_b64: str):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    return load_pem_public_key(build_public_key_pem(public_key_b64).encode("utf-8"))


def rsa_encrypt_chunked(data: bytes, public_key_b64: str = DEFAULT_PUBLIC_KEY) -> bytes:
    """分块 RSA 加密（每块最多 key_size-11 字节），结果顺序拼接。"""
    from cryptography.hazmat.primitives.asymmetric import padding

    pub = _load_public_key(public_key_b64)
    max_chunk = pub.key_size // 8 - 11
    out = bytearray()
    for offset in range(0, len(data), max_chunk):
        out += pub.encrypt(data[offset : offset + max_chunk], padding.PKCS1v15())
    return bytes(out)


def rsa_recover_json(
    encode_res_b64: str, public_key_b64: str = DEFAULT_PUBLIC_KEY
) -> dict[str, Any] | None:
    """用公钥恢复服务端下发的 `encodeRes`，返回解析后的 JSON；失败返回 None。"""
    if not encode_res_b64:
        return None
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import padding

    pub = _load_public_key(public_key_b64)
    raw = base64.b64decode(encode_res_b64)
    data: bytes | None = None
    try:
        data = pub.recover_data_from_signature(raw, padding.PKCS1v15(), None)
    except (InvalidSignature, ValueError, TypeError):
        # 回退：手工做一次裸 RSA 公钥运算并剥离 PKCS#1 v1.5 块。
        numbers = pub.public_numbers()
        size = (numbers.n.bit_length() + 7) // 8
        if len(raw) != size:
            return None
        message = pow(int.from_bytes(raw, "big"), numbers.e, numbers.n)
        buf = message.to_bytes(size, "big")
        if buf[0] != 0x00 or buf[1] != 0x01:
            return None
        sep = buf.find(b"\x00", 2)
        if sep < 0:
            return None
        data = buf[sep + 1 :]
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def decode_encode_res(
    encode_res_b64: str, public_key_b64: str = DEFAULT_PUBLIC_KEY
) -> str:
    """从 `encodeRes` 中取出 `userKey`；取不到返回空串。"""
    payload = rsa_recover_json(encode_res_b64, public_key_b64)
    if not payload:
        return ""
    return str(payload.get("userKey") or "")


def _build_nonce(prefix: str, timestamp: int) -> str:
    return f"{prefix}{secrets.token_hex(16)}:{timestamp}"


def build_special_encode_param(
    public_key_b64: str = DEFAULT_PUBLIC_KEY, timestamp: int | None = None
) -> str:
    """生成 `specialEncodeParam`（未登录 / 无 userKey 时使用）。"""
    ts = now_ms() if timestamp is None else timestamp
    payload = json.dumps(
        {"timestamp": ts, "nonce": _build_nonce(":", ts)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(rsa_encrypt_chunked(payload, public_key_b64)).decode(
        "ascii"
    )


def build_encode_param(
    user_id: str, user_key: str, timestamp: int | None = None
) -> str:
    """生成 `encodeParam`（已登录时使用，以 userKey 为 XXTEA 密钥）。"""
    if not user_key:
        return ""
    ts = now_ms() if timestamp is None else timestamp
    payload = json.dumps(
        {"timestamp": ts, "nonce": _build_nonce(f"{user_id}:", ts)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(xxtea.encrypt(payload, user_key.encode("utf-8"))).decode(
        "ascii"
    )


def decode_camp_payload(
    text: str, user_key: str, *, binary: bool = False
) -> str | bytes:
    """解密营地加密响应体（响应头 `campencrypt: true` 时）。"""
    if not user_key:
        raise ValueError("响应已加密，但登录态缺少 userKey")
    raw = base64.b64decode(text.strip())
    decrypted = xxtea.decrypt(raw, user_key.encode("utf-8"))
    return decrypted if binary else decrypted.decode("utf-8", "replace").rstrip("\x00")
