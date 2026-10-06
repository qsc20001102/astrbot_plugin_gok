"""XXTEA 加密实现（与王者营地客户端协议一致）。

算法与 `Honor-of-Kings-Match-Dashboard/src/lib/camp/xxtea.ts` 逐字节等价，
已用 Node 端参考实现交叉校验（相同 key/明文产出相同密文）。

注意：JS 位运算语义是 32 位有符号/无符号混用，这里统一按 32 位无符号
（掩码 0xFFFFFFFF）运算，XOR/加法结果一致。
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["encrypt", "decrypt"]

_MASK = 0xFFFFFFFF
_DELTA = 0x9E3779B9


def _to_uint32_array(buf: bytes, include_length: bool) -> list[int]:
    """字节 → 小端 32 位字数组；include_length 时在尾部附加原始长度。"""
    words: list[int] = []
    for i in range(0, len(buf), 4):
        chunk = buf[i : i + 4]
        words.append(
            (chunk[0] if len(chunk) > 0 else 0)
            | ((chunk[1] if len(chunk) > 1 else 0) << 8)
            | ((chunk[2] if len(chunk) > 2 else 0) << 16)
            | ((chunk[3] if len(chunk) > 3 else 0) << 24)
        )
    if include_length:
        words.append(len(buf))
    return words


def _to_buffer(words: Sequence[int], include_length: bool) -> bytes:
    """小端 32 位字数组 → 字节；include_length 时按尾部长度字段截断。"""
    size = len(words) << 2
    if include_length:
        length = words[-1]
        if length < 0 or length > size - 4:
            return b""
        size = length
    out = bytearray(size)
    for i in range(size):
        out[i] = (words[i >> 2] >> ((i & 3) << 3)) & 0xFF
    return bytes(out)


def _normalize_key(key: bytes) -> list[int]:
    words = _to_uint32_array(key, False)
    while len(words) < 4:
        words.append(0)
    return words


def _mx(sum_: int, y: int, z: int, p: int, e: int, key: Sequence[int]) -> int:
    a = ((z >> 5) ^ ((y << 2) & _MASK)) & _MASK
    b = ((y >> 3) ^ ((z << 4) & _MASK)) & _MASK
    c = (a + b) & _MASK
    d = ((sum_ ^ y) + (key[(p & 3) ^ e] ^ z)) & _MASK
    return (c ^ d) & _MASK


def encrypt(data: bytes, key: bytes) -> bytes:
    """XXTEA 加密（返回字节，长度已按 4 字节对齐）。"""
    if not data:
        return b""
    words = _to_uint32_array(data, True)
    key_words = _normalize_key(key)
    n = len(words)
    rounds = 6 + 52 // n
    last = n - 1

    total = 0
    z = words[last]
    for _ in range(rounds):
        total = (total + _DELTA) & _MASK
        e = (total >> 2) & 3
        for i in range(last):
            y = words[i + 1]
            words[i] = (words[i] + _mx(total, y, z, i, e, key_words)) & _MASK
            z = words[i]
        y = words[0]
        words[last] = (words[last] + _mx(total, y, z, last, e, key_words)) & _MASK
        z = words[last]
    return _to_buffer(words, False)


def decrypt(data: bytes, key: bytes) -> bytes:
    """XXTEA 解密（按内置长度字段还原原始长度）。"""
    if not data:
        return b""
    words = _to_uint32_array(data, False)
    key_words = _normalize_key(key)
    n = len(words)
    last = n - 1
    rounds = 6 + 52 // n

    total = (rounds * _DELTA) & _MASK
    y = words[0]
    while total != 0:
        e = (total >> 2) & 3
        for i in range(last, 0, -1):
            z = words[i - 1]
            words[i] = (words[i] - _mx(total, y, z, i, e, key_words)) & _MASK
            y = words[i]
        z = words[last]
        words[0] = (words[0] - _mx(total, y, z, 0, e, key_words)) & _MASK
        y = words[0]
        total = (total - _DELTA) & _MASK
    return _to_buffer(words, True)
