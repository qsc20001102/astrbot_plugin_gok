"""各类营地数据解析共用的类型转换与图片资源提取。"""

from __future__ import annotations

import math
import re
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None  # 拒绝 NaN 和无穷值


def _opt_int(source: dict[str, Any], *keys: str) -> int | None:
    """按键顺序取第一个可解析为整数的值；缺失返回 None。"""
    for key in keys:
        value = source.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_str(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else payload


def collect_image_resources(source: Any) -> list[dict[str, str]]:
    """收集营地返回的图片地址，不拼造未知资源链接。

    Args:
        source: 原始营地响应或嵌套字段。

    Returns:
        包含来源字段路径的去重图片地址列表。
    """
    resources: list[dict[str, str]] = []
    seen: set[str] = set()
    pending = [("", source)]
    while pending and len(resources) < 100:
        path, value = pending.pop()
        if isinstance(value, dict):
            pending.extend(
                (f"{path}.{key}".strip("."), item) for key, item in value.items()
            )
        elif isinstance(value, list):
            pending.extend(
                (f"{path}.{index}", item) for index, item in enumerate(value)
            )
        elif isinstance(value, str) and value.startswith(("https://", "http://")):
            key = path.rsplit(".", 1)[-1].lower()
            if value not in seen and (
                key.endswith(("icon", "img", "image"))
                or re.search(
                    r"\.(?:png|jpe?g|webp|gif|svg)(?:[?#]|$)", value, re.IGNORECASE
                )
            ):
                seen.add(value)
                resources.append({"path": path, "url": value})
    return resources
