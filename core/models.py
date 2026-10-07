"""把营地原始响应规范化成插件内部模型。

营地接口的字段名在不同模式/版本间有多个别名（`killcnt`/`kills`、
`AcntCamp`/`acntCamp` 等），这里统一收口，上层只面对 `PlayerProfile` /
`MatchRecord`，不再关心字段差异。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .heroes import hero_repository, strip_control_chars
from .rank import rank_name_from_code, strip_rank_stars

__all__ = [
    "PlayerProfile",
    "MatchRecord",
    "SeasonStats",
    "BRANCH_NAMES",
    "detect_mode",
    "MODE_NAMES",
    "parse_profile",
    "parse_season_stats",
    "parse_battle_row",
    "build_battle_comment",
    "collect_image_resources",
]

# 对局详情里的分路代码 → 名称。
# 注意：这套编码与官方 herolist.json 的 `roles` 不同（3/4 含义相反），
# 见 heroes.HERO_ROLE_NAMES，两者不可混用。
BRANCH_NAMES: dict[int, str] = {
    1: "对抗路",
    2: "打野",
    3: "发育路",
    4: "中路",
    5: "游走",
    10: "游走",
}

MODE_NAMES: dict[str, str] = {
    "ranked": "排位赛",
    "peak": "巅峰赛",
    "fun": "娱乐/匹配",
    "other": "其它模式",
}

# evaluateUrlV3 文件名 hash → 官方分路奖牌名。
# 该图比 silver_/gold_ 之类的旧命名更准，可区分铜牌与银牌。
_EVALUATE_V3_MEDALS: dict[str, str] = {
    "116bb42c52b7d83b9d80ac9dd9580607": "银牌对抗路",
    "e8602ae4b427f06dd1349438fbeab68f": "铜牌对抗路",
    "c30089b8daf9a4792f85c8a6d97a3e9c": "金牌对抗路",
    "a2c96893471637e5cf5c0a1e2c9829f3": "银牌中路",
    "977937945942799fd618773e5c378d3a": "银牌游走",
    "3159d2f1733203167a9a3d5d3e4656ad": "铜牌游走",
    "c717aab51e99a4bfa9c6d2e024e97512": "金牌发育路",
    "7577421618c781e7a59b81904937a8a0": "银牌发育路",
    "1147db2cd2a46031783a9a0fc34f7f3c": "金牌游走",
    "af6fd95b08fd1b58340b48374707262c": "铜牌发育路",
    "029706c958a71f2aa5c187e2ef021430": "铜牌中路",
    "39d8211165f3730700fc6db10abd170e": "银牌打野",
    "f63de8a7f98863ab3a34aada6bc4bd6f": "金牌中路",
    "5142af35177e111837efbf85071f373b": "金牌打野",
    "c8a09fe55b4614d0307a6161f32ae479": "铜牌打野",
    "a8b5101bc81ae64cf96c67ed1ab21975": "顶级游走",
    "926ba0111984464ad46e72dc93157fcd": "顶级发育路",
    "5db4fef1bfc72dd2c5ae71b01ef3951b": "顶级对抗路",
}

_MEDAL_URL_RE = re.compile(
    r"\b(top|gold|silver|bronze)[-_](warrior|mage|assassin|support|shooter|archer|tank)\b",
    re.IGNORECASE,
)
_MEDAL_TIERS = {"top": "顶级", "gold": "金牌", "silver": "银牌", "bronze": "铜牌"}
_MEDAL_CLASSES = {
    "warrior": "战士",
    "mage": "法师",
    "assassin": "刺客",
    "support": "辅助",
    "shooter": "射手",
    "archer": "射手",
    "tank": "坦克",
}


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
    return result if result == result else None  # 过滤 NaN


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
    """Collect image URLs supplied by Camp, without generating asset URLs.

    Args:
        source: An original Camp response or one of its nested records.

    Returns:
        Unique image URLs with their source paths for optional presentation.
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


def detect_mode(map_name: str) -> str:
    """按模式名归类对局。"""
    if not map_name:
        return "other"
    if "排位" in map_name:
        return "ranked"
    if "巅峰" in map_name:
        return "peak"
    if "匹配" in map_name or "娱乐" in map_name or "5v5" in map_name:
        return "fun"
    return "other"


# ---------------------------------------------------------------------- 数据模型
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
    # 营地 `hideMatch=1` 表示该玩家隐藏了战绩；此时战绩接口返回空列表而非报错
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


@dataclass
class MatchRecord:
    """一场对局。"""

    external_id: str = ""
    played_at: datetime = field(default_factory=datetime.now)
    mode: str = "other"
    mode_name: str = ""
    hero_id: str = ""
    hero_name: str = "未知英雄"
    hero_icon: str = ""
    result: str = "lose"
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    score: float = 0.0
    duration_sec: int = 0
    rank_code: int | None = None
    rank_name: str = ""
    stars: int = 0
    peak_score: int | None = None
    peak_delta: int | None = None
    mvp: bool = False
    gold: bool = False
    mvp_type: str = ""
    mvp_icon: str = ""
    medal: str = ""
    medal_icon: str = ""
    evaluate: str = ""
    side: str = ""
    economy: int | None = None
    damage: int | None = None
    # 供「补全详情」阶段使用的原始字段
    game_seq: str = ""
    game_svr: str = ""
    relay_svr: str = ""
    battle_type: int = 0
    image_resources: list[dict[str, str]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------ 展示辅助
    @property
    def kda(self) -> float:
        return round((self.kills + self.assists) / max(1, self.deaths), 1)

    @property
    def win(self) -> bool:
        return self.result == "win"

    @property
    def result_text(self) -> str:
        return "胜利" if self.win else "失败"

    @property
    def duration_text(self) -> str:
        minutes, seconds = divmod(max(0, self.duration_sec), 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def played_at_text(self) -> str:
        return self.played_at.strftime("%Y-%m-%d %H:%M")

    @property
    def honor_text(self) -> str:
        """本条对局的荣誉文案：MVP / 金牌 / 奖牌。"""
        parts: list[str] = []
        if self.mvp_type == "mvp":
            parts.append("MVP")
        elif self.mvp_type == "svp":
            parts.append("败方MVP")
        if self.medal:
            parts.append(self.medal)
        elif self.gold:
            parts.append("金牌")
        return " · ".join(parts)

    @property
    def score_text(self) -> str:
        return f"{self.score:.1f}" if self.score else "-"

    def to_dict(self, detailed: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "external_id": self.external_id,
            "played_at": self.played_at_text,
            "mode": self.mode,
            "mode_name": self.mode_name or MODE_NAMES.get(self.mode, "其它模式"),
            "hero_id": self.hero_id,
            "hero_name": self.hero_name,
            "hero_icon": self.hero_icon,
            "result": self.result,
            "result_text": self.result_text,
            "win": self.win,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "kda": self.kda,
            "score": self.score,
            "score_text": self.score_text,
            "duration_sec": self.duration_sec,
            "duration_text": self.duration_text,
            "rank_name": self.rank_name,
            "stars": self.stars,
            "peak_score": self.peak_score,
            "peak_delta": self.peak_delta,
            "mvp": self.mvp,
            "mvp_type": self.mvp_type,
            "mvp_icon": self.mvp_icon,
            "gold": self.gold,
            "medal": self.medal,
            "medal_icon": self.medal_icon,
            "evaluate": self.evaluate,
            "honor_text": self.honor_text,
            "side": self.side,
            "game_seq": self.game_seq,
            "game_svr": self.game_svr,
            "relay_svr": self.relay_svr,
            "battle_type": self.battle_type,
            "economy": self.economy,
            "damage": self.damage,
            "image_resources": self.image_resources,
        }
        if detailed:
            data.update(
                {
                    "economy": self.economy,
                    "damage": self.damage,
                    "game_seq": self.game_seq,
                }
            )
        return data


# ---------------------------------------------------------------------- 解析
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
    # hideMatch=1：该角色隐藏了战绩，战绩接口会返回空列表
    hide_match = bool(_as_int(role.get("hideMatch"), 0)) or bool(
        _as_int(data.get("hideMatch"), 0)
    )

    return PlayerProfile(
        camp_id=camp_id or str(data.get("targetUserId") or ""),
        nickname=nickname,
        avatar=_first_str(role, "roleIcon", "avatar"),
        area=_parse_area(area_text),
        area_text=area_text,
        role_id=str(role.get("roleId") or ""),
        server_name=_first_str(role, "serverName"),
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


def parse_honors(row: dict[str, Any]) -> dict[str, Any]:
    """解析一场对局的荣誉（MVP/SVP、金银铜牌）。"""
    evaluate = _first_str(row, "desc", "evaluate")
    url_blob = " ".join(
        str(row.get(key) or "")
        for key in (
            "evaluateUrl",
            "evaluateUrlV2",
            "evaluateUrlV3",
            "mvpUrlV2",
            "mvpUrlV3",
        )
    )

    mvp_type = ""
    if re.search(r"/svp\.png", url_blob, re.IGNORECASE) or re.search(
        r"\bsvp\b", url_blob, re.IGNORECASE
    ):
        mvp_type = "svp"
    elif (
        re.search(r"/mvp\.png", url_blob, re.IGNORECASE)
        or bool(row.get("mvp"))
        or "MVP" in evaluate
    ):
        mvp_type = "mvp"

    mvp_icon = _first_str(row, "mvpUrlV3", "mvpUrlV2")

    medal_icon = _first_str(row, "evaluateUrlV3")
    v3_hash = ""
    if medal_icon:
        tail = medal_icon.rsplit("/", 1)[-1]
        v3_hash = re.sub(r"\.png$", "", tail, flags=re.IGNORECASE)
    medal = _EVALUATE_V3_MEDALS.get(v3_hash, "")

    if not medal:
        match = _MEDAL_URL_RE.search(url_blob)
        if match:
            tier = _MEDAL_TIERS.get(match.group(1).lower(), "")
            branch_num = _as_int(row.get("branchEvaluate"), -1)
            role = BRANCH_NAMES.get(branch_num) or _MEDAL_CLASSES.get(
                match.group(2).lower(), ""
            )
            if tier and role:
                medal = f"{tier}{role}"

    gold = bool(
        row.get("gold")
        or (medal.startswith("金牌") if medal else False)
        or re.search(r"[-_]gold[-_]|/gold_", url_blob, re.IGNORECASE)
    )

    return {
        "evaluate": evaluate,
        "mvp": bool(mvp_type),
        "mvp_type": mvp_type,
        "mvp_icon": mvp_icon,
        "gold": bool(gold),
        "medal": medal,
        "medal_icon": medal_icon,
    }


def _parse_played_at(row: dict[str, Any], index: int) -> datetime:
    """优先用 unix 时间戳；`gametime` 可能只是 "12:44"，不可靠。"""
    for key in ("dtEventTime", "dteventtime", "battle_time"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        text = str(raw)
        if text.isdigit():
            value = int(text)
            # 10 位为秒，13 位为毫秒
            seconds = value if len(text) == 10 else value / 1000
            try:
                return datetime.fromtimestamp(seconds, ZoneInfo("Asia/Shanghai"))
            except (OverflowError, OSError, ValueError):
                continue

    game_time = _first_str(row, "gametime", "gameTime")
    if game_time and not re.fullmatch(r"\d{1,2}:\d{2}", game_time):
        for fmt in ("%Y-%m-%d %H:%M", "%m-%d %H:%M", "%Y/%m/%d %H:%M"):
            try:
                parsed = datetime.strptime(game_time, fmt)
                if fmt.startswith("%m"):
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue

    return datetime.now() - timedelta(hours=index)


def parse_battle_row(row: dict[str, Any], index: int = 0) -> MatchRecord:
    """把一行战绩规范化为 `MatchRecord`。"""
    mode_name = _first_str(row, "mapName", "map_name") or "未知模式"
    result_raw = row.get("gameresult", row.get("gameResult", row.get("result")))
    result = (
        "win"
        if result_raw in (1, "1")
        or "胜" in str(result_raw)
        or str(result_raw).lower() == "win"
        else "lose"
    )

    hero_id = _first_str(row, "heroId", "hero_id")
    hero_name = hero_repository.name(
        hero_id, fallback=_first_str(row, "heroName", "hero_name", "chessName")
    )

    rank_code_raw = _as_int(row.get("roleJob"), -1)
    rank_code = rank_code_raw if rank_code_raw >= 0 else None
    # roleJobName is the current profile rank even on historical records.
    rank_name = rank_name_from_code(rank_code) or ""
    stars = _as_int(row.get("stars"), -1)
    if stars < 0:
        match = re.search(r"(\d+)\s*星", rank_name)
        stars = int(match.group(1)) if match else 0

    new_peak = _as_int(row.get("newMasterMatchScore"), -1)
    old_peak = _as_int(row.get("oldMasterMatchScore"), -1)
    peak_score = new_peak if new_peak > 0 else None
    peak_delta = new_peak - old_peak if new_peak >= 0 and old_peak >= 0 else None

    camp_value = row.get("AcntCamp", row.get("acntCamp", row.get("acnt_camp")))
    camp_number = _as_int(camp_value, -1)
    side = "blue" if camp_number == 1 else "red" if camp_number == 2 else ""

    honors = parse_honors(row)
    score = _as_float(row.get("gradeGame"))
    if score is None:
        score = _as_float(row.get("score")) or 0.0

    duration = _as_int(row.get("usedTime"), -1)
    if duration < 0:
        duration = _as_int(row.get("durationSec"), 0)

    game_seq = _first_str(row, "gameSeq", "battleId", "battle_id")
    external_id = game_seq or "-".join(
        str(row.get(key) or "")
        for key in ("dtEventTime", "heroId", "killcnt", "deadcnt", "assistcnt")
    )

    return MatchRecord(
        external_id=external_id,
        played_at=_parse_played_at(row, index),
        mode=detect_mode(mode_name),
        mode_name=mode_name,
        hero_id=hero_id,
        hero_name=hero_name,
        hero_icon=_first_str(row, "heroIcon", "hero_icon"),
        image_resources=collect_image_resources(row),
        result=result,
        kills=_as_int(row.get("killcnt", row.get("kills"))),
        deaths=_as_int(row.get("deadcnt", row.get("deaths"))),
        assists=_as_int(row.get("assistcnt", row.get("assists"))),
        score=round(score, 1) if score else 0.0,
        duration_sec=max(0, duration),
        rank_code=rank_code,
        rank_name=rank_name,
        stars=max(0, stars),
        peak_score=peak_score,
        peak_delta=peak_delta,
        mvp=honors["mvp"],
        gold=honors["gold"],
        mvp_type=honors["mvp_type"],
        mvp_icon=honors["mvp_icon"],
        medal=honors["medal"],
        medal_icon=honors["medal_icon"],
        evaluate=honors["evaluate"],
        side=side,
        economy=_opt_int(row, "economy"),
        damage=_opt_int(row, "hurtTotal", "damage"),
        game_seq=game_seq,
        game_svr=_first_str(row, "gameSvrId", "gameSvr"),
        relay_svr=_first_str(row, "relaySvrId", "relaySvr"),
        battle_type=_as_int(row.get("battleType")),
        raw=row,
    )


def build_battle_comment(
    matches: list[MatchRecord], limit: int = 10
) -> list[dict[str, Any]]:
    """为 LLM 锐评提取精简战绩（字段名保持原样以便提示词解释）。"""
    comment: list[dict[str, Any]] = []
    for match in matches[:limit]:
        comment.append(
            {
                "gametime": match.played_at_text,
                "mapName": match.mode_name,
                "heroName": match.hero_name,
                "killcnt": match.kills,
                "deadcnt": match.deaths,
                "assistcnt": match.assists,
                "gameresult": 1 if match.win else 2,
                "mvpcnt": 1 if match.mvp_type == "mvp" else 0,
                "losemvp": 1 if match.mvp_type == "svp" else 0,
                "gradeGame": match.score,
                "medal": match.medal,
            }
        )
    return comment
