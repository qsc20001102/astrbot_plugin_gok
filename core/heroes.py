"""英雄元数据：营地 heroId → 中文名 / 分路。

营地战绩里 `heroId` 就是官方 `herolist.json` 的 `ename`，因此这份随包数据
（`data/heroes.json`，来源 pvp.qq.com 官方静态文件）即可离线解析英雄名，
不需要在运行时依赖外部接口。未知 ID 时回退为「英雄{id}」。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["HeroRepository", "hero_repository", "strip_control_chars"]

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "heroes.json"

# hero_type 数值 → 名称
HERO_TYPES: dict[int, str] = {
    1: "战士",
    2: "法师",
    3: "坦克",
    4: "刺客",
    5: "射手",
    6: "辅助",
}

# 官方 herolist.json 里 `roles` 字段的分路代码 → 名称。
# 注意：这套编码与对局详情里的 `branchEvaluate` **不同**（3/4 含义相反），
# 后者见 models.BRANCH_NAMES，两者不可混用。
HERO_ROLE_NAMES: dict[int, str] = {
    1: "对抗路",
    2: "打野",
    3: "中路",
    4: "发育路",
    5: "游走",
}


def strip_control_chars(text: str) -> str:
    """去掉昵称里可能携带的控制字符。"""
    return "".join(ch for ch in text if ch >= " " or ch == "\t").strip()


class HeroRepository:
    """Built-in offline hero catalog."""

    def __init__(self, path: Path = _DATA_PATH) -> None:
        self.path = path
        self._heroes: dict[str, dict[str, Any]] | None = None

    def load(self) -> dict[str, dict[str, Any]]:
        if self._heroes is not None:
            return self._heroes
        try:
            # utf-8-sig：容忍带 BOM 的文件（历史上由 PowerShell 生成过）。
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            heroes = raw.get("heroes") if isinstance(raw, dict) else None
            self._heroes = heroes if isinstance(heroes, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "加载英雄目录失败(%s)，英雄名将回退为 ID", type(exc).__name__
            )
            self._heroes = {}
        return self._heroes

    def name(self, hero_id: Any, fallback: str = "") -> str:
        """返回英雄中文名；未知时返回 `fallback` 或「英雄{id}」。"""
        if hero_id in (None, ""):
            return fallback or "未知英雄"
        key = str(hero_id)
        entry = self.load().get(key)
        if entry and entry.get("name"):
            return str(entry["name"])
        return fallback or f"英雄{key}"

    def info(self, hero_id: Any) -> dict[str, Any]:
        if hero_id in (None, ""):
            return {}
        return self.load().get(str(hero_id), {})

    def role_name(self, hero_id: Any) -> str:
        """按官方 `roles` 字段给出主要分路名（可能为空）。"""
        entry = self.info(hero_id)
        roles = str(entry.get("roles") or "")
        first = roles.split("|")[0].strip() if roles else ""
        if first.isdigit():
            return HERO_ROLE_NAMES.get(int(first), "")
        return ""

    def type_name(self, hero_id: Any) -> str:
        entry = self.info(hero_id)
        hero_type = entry.get("type")
        if isinstance(hero_type, int):
            return HERO_TYPES.get(hero_type, "")
        return ""

    def all_names(self) -> list[str]:
        return sorted(str(v.get("name")) for v in self.load().values() if v.get("name"))

    @property
    def count(self) -> int:
        return len(self.load())


hero_repository = HeroRepository()
