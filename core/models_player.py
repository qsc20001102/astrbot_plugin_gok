"""玩家主页与赛季统计模型及其解析。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .heroes import hero_repository, strip_control_chars
from .model_utils import (
    _as_dict,
    _as_float,
    _as_int,
    _as_list,
    _first_str,
    _unwrap,
    collect_image_resources,
)
from .rank import strip_rank_stars


@dataclass
class PlayerProfile:
    """玩家概况。"""

    camp_id: str = ""
    nickname: str = "未知"
    avatar: str = ""
    area: str = "wechat"
    area_text: str = ""
    role_id: str = ""
    server_name: str = ""
    # gameOnline 是三态数值；缺失及未知码不默认当作离线。
    game_online: int | None = None
    current_rank: str = "未知"
    rank_icon: str = ""
    rank_stars_icon: str = ""
    current_stars: int = 0
    season_games: int = 0
    season_wins: int = 0
    rank_score: int = 0
    peak_rating: int = 0
    peak_score: int = 0
    mvp_count: int = 0
    gold_count: int = 0
    # In-game privacy flag; Camp battle visibility requires an actual list query.
    hide_match: bool = False
    bg_img: str = ""
    game_bg_img: str = ""
    image_resources: list[dict[str, str]] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        if self.season_games <= 0:
            return 0.0
        return round(self.season_wins / self.season_games * 100, 1)

    @property
    def area_name(self) -> str:
        return {"wechat": "微信区", "qq": "QQ区"}.get(self.area, self.area)

    @property
    def game_status(self) -> str:
        """按统一约定生成游戏状态文案。

        Returns:
            离线、在线、游戏中或未知。
        """
        return {0: "离线", 1: "在线", 2: "游戏中"}.get(self.game_online, "未知")

    @property
    def rank_label(self) -> str:
        return strip_rank_stars(self.current_rank) or "未知"

    @property
    def rank_score_total(self) -> int:
        from .rank import parse_rank_score

        return parse_rank_score(self.current_rank, self.current_stars)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camp_id": self.camp_id,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "area": self.area,
            "area_name": self.area_name,
            "role_id": self.role_id,
            "server_name": self.server_name,
            "game_online": self.game_online,
            "game_status": self.game_status,
            "current_rank": self.rank_label,
            "current_stars": self.current_stars,
            "rank_label": self.rank_label,
            "rank_icon": self.rank_icon,
            "rank_stars_icon": self.rank_stars_icon,
            "season_games": self.season_games,
            "season_wins": self.season_wins,
            "win_rate": self.win_rate,
            "rank_score": self.rank_score,
            "peak_rating": self.peak_rating,
            "peak_score": self.peak_score,
            "mvp_count": self.mvp_count,
            "gold_count": self.gold_count,
            "hide_match": self.hide_match,
            "bg_img": self.bg_img,
            "game_bg_img": self.game_bg_img,
            "image_resources": self.image_resources,
        }


@dataclass
class SeasonStats:
    """赛季页统计（可能缺项）。"""

    season_games: int | None = None
    season_wins: int | None = None
    gold_count: int | None = None
    rank_score: int | None = None
    peak_rating: int | None = None
    peak_score: int | None = None
    season_name: str = ""
    peak_games: int = 0
    # 营地直接给出的本赛季英雄统计，比本地聚合更准
    heroes: list[dict[str, Any]] = field(default_factory=list)


def parse_profile(payload: dict[str, Any], camp_id: str = "") -> PlayerProfile:
    """解析 `/game/koh/profile` 响应。"""
    data = _unwrap(payload)
    target_role_id = str(data.get("targetRoleId") or "")
    roles = [r for r in _as_list(data.get("roleList")) if isinstance(r, dict)]
    role: dict[str, Any] = {}
    if target_role_id:
        role = next(
            (r for r in roles if str(r.get("roleId") or "") == target_role_id), {}
        )
    if not role and roles:
        role = roles[0]

    # 段位取 head.mods 里的 5v5 排位模块（modId 701 或名称含「排位」）
    head = _as_dict(data.get("head"))
    mods = [m for m in _as_list(head.get("mods")) if isinstance(m, dict)]
    mode_5v5 = next(
        (m for m in mods if _as_int(m.get("modId"), -1) == 701), None
    ) or next((m for m in mods if "排位" in str(m.get("name") or "")), None)

    rank_name = ""
    rank_icon = _first_str(role, "roleJobIcon")
    rank_stars_icon = ""
    stars = 0
    if mode_5v5:
        rank_name = str(mode_5v5.get("name") or "")
        rank_icon = _first_str(mode_5v5, "icon") or rank_icon
        try:
            param = json.loads(str(mode_5v5.get("param1") or "{}"))
            stars = _as_int(_as_dict(param).get("rankingStar"))
            rank_stars_icon = _first_str(_as_dict(param), "starImg")
        except (ValueError, TypeError):
            stars = 0
        # 星数单独保存，段位名去掉尾部的「N星」避免重复展示
        rank_name = strip_rank_stars(rank_name)

    area_text = _first_str(role, "areaName", "roleText")
    nickname = strip_control_chars(
        _first_str(role, "roleName", "nickname") or f"营地{camp_id}"
    )
    # Preserve the privacy hint without inferring Camp battle visibility from it.
    hide_match = bool(_as_int(role.get("hideMatch"), 0)) or bool(
        _as_int(data.get("hideMatch"), 0)
    )
    state = str(role.get("gameOnline")).strip()
    game_online = int(state) if state in {"0", "1", "2"} else None

    return PlayerProfile(
        camp_id=camp_id or str(data.get("targetUserId") or ""),
        nickname=nickname,
        avatar=_first_str(role, "roleIcon", "avatar"),
        area=_parse_area(area_text),
        area_text=area_text,
        role_id=str(role.get("roleId") or ""),
        server_name=_first_str(role, "serverName"),
        game_online=game_online,
        current_rank=rank_name or "未知",
        rank_icon=rank_icon,
        rank_stars_icon=rank_stars_icon,
        current_stars=stars,
        hide_match=hide_match,
        bg_img=_first_str(data, "bgImg"),
        game_bg_img=_first_str(data, "gameBgImg"),
        image_resources=collect_image_resources(data),
    )


def _parse_area(text: str) -> str:
    if "微信" in text or re.search(r"wx", text, re.IGNORECASE):
        return "wechat"
    if "Q" in text or re.search(r"qq", text, re.IGNORECASE):
        return "qq"
    return "wechat"


def parse_season_stats(payload: dict[str, Any]) -> SeasonStats | None:
    """解析 `/game/seasonpage` 响应；无有效数据时返回 None。"""
    data = _unwrap(payload)
    history = [h for h in _as_list(data.get("historyList")) if isinstance(h, dict)]
    if not history:
        return None
    current = history[0]
    rank_info = _as_dict(current.get("rankInfo"))
    master_info = _as_dict(current.get("masterInfo"))
    head_card = _as_dict(data.get("headCard"))
    if not rank_info and not master_info and not head_card:
        return None

    season_games = _as_int(rank_info.get("totalCnt"))
    season_wins = _as_int(rank_info.get("totalWinCnt"))
    rank_avg = _as_float(rank_info.get("averageScore"))
    peak_avg = _as_float(master_info.get("averageScore"))
    peak_games = _as_int(master_info.get("totalCnt"))
    master_score_raw = _as_float(master_info.get("masterScore"))

    # 巅峰分：真实分数优先；只有确实打过巅峰赛（totalCnt>0）时才用 1200 起始分兜底，
    # 否则会把「没打过巅峰」显示成 1200 分。
    peak_score: int | None = None
    if master_score_raw and master_score_raw > 0:
        peak_score = round(master_score_raw)
    elif peak_games > 0:
        peak_score = 1200

    has_games = season_games > 0
    has_ratings = bool(
        (rank_avg and rank_avg > 0)
        or (peak_avg and peak_avg > 0)
        or (peak_score is not None)
    )
    if not has_games and not has_ratings:
        return None

    # 本赛季英雄统计：营地直接给出，比本地聚合更权威
    heroes: list[dict[str, Any]] = []
    for item in _as_list(rank_info.get("heros")):
        row = _as_dict(item)
        hero_id = row.get("heroId")
        if hero_id in (None, ""):
            continue
        games = _as_int(row.get("gameCnt"))
        wins = _as_int(row.get("winCnt"))
        raw_rate = _as_float(row.get("winRate"))
        if raw_rate is None or raw_rate > 1:  # 营地给的可能是 0–1 也可能是百分比
            win_rate = round(wins / games * 100, 1) if games else 0.0
        else:
            win_rate = round(raw_rate * 100, 1)
        heroes.append(
            {
                "hero_id": str(hero_id),
                "hero_name": str(row.get("heroName") or hero_repository.name(hero_id)),
                "hero_icon": str(row.get("heroIcon") or ""),
                "games": games,
                "wins": wins,
                "win_rate": win_rate,
                "fight_power": _as_int(row.get("heroFightPower")) or None,
            }
        )

    return SeasonStats(
        season_games=season_games if has_games else None,
        season_wins=season_wins if has_games else None,
        gold_count=_as_int(rank_info.get("goldCnt")) or None,
        rank_score=round(rank_avg) if rank_avg and rank_avg > 0 else None,
        peak_rating=round(peak_avg) if peak_avg and peak_avg > 0 else None,
        peak_score=peak_score,
        season_name=str(current.get("seasonName") or ""),
        peak_games=peak_games,
        heroes=heroes,
    )
