"""近期战绩模型与荣誉解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .heroes import hero_repository
from .model_utils import (
    _as_float,
    _as_int,
    _first_str,
    _opt_int,
    collect_image_resources,
)
from .rank import rank_name_from_code

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


@dataclass
class MatchRecord:
    """一场对局。"""

    external_id: str = ""
    played_at: datetime | None = None
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
        return {"win": "胜利", "lose": "失败"}.get(self.result, "结果未返回")

    @property
    def duration_text(self) -> str:
        minutes, seconds = divmod(max(0, self.duration_sec), 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def played_at_text(self) -> str:
        return (
            self.played_at.strftime("%Y-%m-%d %H:%M")
            if self.played_at
            else "时间未返回"
        )

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
            "kill_streaks": [
                {"label": label, "count": _as_int(self.raw.get(key))}
                for key, label in (
                    ("hero1TripleKillCnt", "三杀"),
                    ("hero1UltraKillCnt", "四杀"),
                    ("hero1RampageCnt", "五杀"),
                    ("hero1Kill6Cnt", "六连击"),
                    ("hero1Kill7Cnt", "七连击"),
                    ("hero1Kill8Cnt", "八连击"),
                    ("hero1Kill9Cnt", "九连击"),
                    ("hero1Kill10Cnt", "十连击"),
                )
                if _as_int(self.raw.get(key)) > 0
            ],
            "first_blood": _as_int(self.raw.get("firstBlood")) == 1,
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


def _parse_played_at(row: dict[str, Any], index: int) -> datetime | None:
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

    return None


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
        if result_raw in (2, "2", "lose") or "败" in str(result_raw)
        else "unknown"
    )

    hero_id = _first_str(row, "heroId", "hero_id")
    hero_name = hero_repository.name(
        hero_id, fallback=_first_str(row, "heroName", "hero_name", "chessName")
    )

    rank_code_raw = _as_int(row.get("roleJob"), -1)
    rank_code = rank_code_raw if rank_code_raw >= 0 else None
    # roleJobName 在历史战绩中也可能是当前主页段位，不能当作对局当时的段位。
    rank_name = rank_name_from_code(rank_code) or ""
    stars = _as_int(row.get("stars"), -1)
    if stars < 0:
        match = re.search(r"(\d+)\s*星", rank_name)
        stars = int(match.group(1)) if match else 0

    new_peak = _as_int(row.get("newMasterMatchScore"), -1)
    old_peak = _as_int(row.get("oldMasterMatchScore"), -1)
    peak_score = new_peak if new_peak > 0 else None
    peak_delta = new_peak - old_peak if new_peak > 0 and old_peak > 0 else None

    camp_value = row.get("AcntCamp", row.get("acntCamp", row.get("acnt_camp")))
    camp_number = _as_int(camp_value, -1)
    side = "blue" if camp_number == 1 else "red" if camp_number == 2 else ""

    honors = parse_honors(row)
    score = _as_float(row.get("gradeGame"))
    if score is None:
        score = _as_float(row.get("score")) or 0.0

    duration = _as_int(row.get("usedTime", row.get("usedtime")), -1)
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
