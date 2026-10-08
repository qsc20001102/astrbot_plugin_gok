"""构造和解析已经验证的营地昵称搜索 Protobuf 消息。"""

from __future__ import annotations

from typing import Any


def _varint(value: int) -> bytes:
    """编码非负整数为 Protobuf varint。

    Args:
        value: 待编码或转换的值。

    Returns:
        编码后的字节。
    """
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def build_search_request(nickname: str) -> bytes:
    """构造已验证的营地昵称搜索请求。

    Args:
        nickname: 用户提供的搜索昵称。

    Returns:
        符合已确认字段编号的 Protobuf 原始字节。
    """
    name = nickname.encode("utf-8")
    return (
        b"\x08"
        + _varint(1011)
        + b"\x12"
        + _varint(len(name))
        + name
        + b"\x18\x01\x20\x0a\x3a\x01\x30"
    )


def _read_varint(raw: bytes, offset: int) -> tuple[int, int]:
    """读取有边界保护的 varint。

    Args:
        raw: 原始 Protobuf 响应字节。
        offset: 字节读取起点。

    Returns:
        整数值与读取后的字节位置。
    """
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(raw):
            raise ValueError("Truncated Protobuf varint")
        byte = raw[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise ValueError("Protobuf varint exceeds 64 bits")
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError("Invalid Protobuf varint")


def _fields(raw: bytes) -> dict[int, list[int | bytes]]:
    """检查消息长度和 wire type 后读取重复字段。

    Args:
        raw: 原始 Protobuf 响应字节。

    Returns:
        以字段号、类型和字段值表示的消息内容。
    """
    output: dict[int, list[int | bytes]] = {}
    offset = 0
    while offset < len(raw):
        tag, offset = _read_varint(raw, offset)
        number, wire = tag >> 3, tag & 7
        if not 0 < number < 1 << 29:
            raise ValueError("Invalid Protobuf field number")
        if wire == 0:
            value, offset = _read_varint(raw, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, offset = _read_varint(raw, offset)
            else:
                size = 8 if wire == 1 else 4
            if offset + size > len(raw):
                raise ValueError("Truncated Protobuf field")
            value = raw[offset : offset + size]
            offset += size
        else:
            raise ValueError("Unsupported Protobuf wire type")
        output.setdefault(number, []).append(value)
    return output


def parse_search_response(raw: bytes) -> dict[str, Any]:
    """解析搜索用户与已经观测到的业务状态。

    Args:
        raw: 原始 Protobuf 响应字节。

    Returns:
        业务状态与解析后的搜索用户集合。
    """
    root = _fields(raw)
    statuses = root.get(2, [])
    if not statuses or not isinstance(statuses[0], bytes):
        raise ValueError("Missing Camp search status")
    status = statuses[0].decode("utf-8")
    if status != "success":
        return {"returnCode": -1, "returnMsg": status or "营地昵称搜索失败"}
    messages = [root]
    for number in (3, 1, 25, 2):
        messages = [
            _fields(value)
            for fields in messages
            for value in fields.get(number, [])
            if isinstance(value, bytes)
        ]
    users = []
    seen: set[str] = set()
    for detail in messages:
        user: dict[str, str] = {}
        for key, number, numeric in (
            ("uid", 17, True),
            ("name", 2, False),
            ("avatar", 3, False),
            ("level", 10, True),
            ("dw", 28, False),
            ("region", 37, False),
        ):
            value = detail.get(number, [b""])[0]
            user[key] = (
                str(value)
                if numeric and isinstance(value, int)
                else (value.decode("utf-8") if isinstance(value, bytes) else "")
            )
        uid = user["uid"]
        if uid.isascii() and uid.isdigit() and 5 <= len(uid) <= 15 and uid not in seen:
            seen.add(uid)
            users.append(user)
    return {"returnCode": 0, "data": {"users": users}}
