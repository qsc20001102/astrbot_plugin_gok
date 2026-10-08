"""段位换算：把段位名 + 星数折算成可比较的累计星数。

折算规则（与参考实现 `src/lib/rank.ts` 一致）：青铜III 0 星 = 0，每颗星 +1，
星耀I 满星（累计 100 星）再赢一场即「王者 1 星」，王者段位继续按星数累加。
这样相邻两场排位的分数差恰好等于星数变化，跨小段与跨大段晋级都成立。

Live Camp responses return the current rank in roleJobName for historical
matches. Use the per-match roleJob code; never use roleJobName as a fallback.
"""

from __future__ import annotations

import re

__all__ = [
    "KING_BASE",
    "KING_RANK_CODE",
    "MAX_PLAUSIBLE_STAR_DELTA",
    "strip_rank_stars",
    "parse_rank_score",
    "format_rank_label",
    "rank_name_from_code",
    "rank_score_from_code",
    "score_to_approx_label",
]

KING_BASE = 100
KING_RANK_CODE = 16

# 相邻两场排位星数差超过该值视为断点（赛季重置/继承掉段），不作为单场变化展示。
MAX_PLAUSIBLE_STAR_DELTA = 10

# 王者以下的段位结构：(名称, 小段数, 每小段星数)
_SUB_KING_RANKS: list[tuple[str, int, int]] = [
    ("青铜", 3, 3),
    ("白银", 3, 3),
    ("黄金", 4, 4),
    ("铂金", 4, 4),
    ("钻石", 5, 5),
    ("星耀", 5, 5),
]

# 段位名 → 起始累计星数
_RANK_BASE: dict[str, int] = {}
_base = 0
for _name, _tiers, _stars in _SUB_KING_RANKS:
    _RANK_BASE[_name] = _base
    _base += _tiers * _stars

# 小段位写法：ASCII 罗马数字（IV 必须排在 I/V 之前，避免子串误匹配）、
# 罗马字符、中文数字、阿拉伯数字。
_TIER_TOKENS: list[tuple[str, int]] = [
    ("IV", 4),
    ("III", 3),
    ("II", 2),
    ("V", 5),
    ("I", 1),
    ("Ⅴ", 5),
    ("Ⅳ", 4),
    ("Ⅲ", 3),
    ("Ⅱ", 2),
    ("Ⅰ", 1),
    ("五", 5),
    ("四", 4),
    ("三", 3),
    ("二", 2),
    ("一", 1),
    ("5", 5),
    ("4", 4),
    ("3", 3),
    ("2", 2),
    ("1", 1),
]

# 对局段位代码 → 段位名（代码不连续，顺序由升降段实证得出）。
_MATCH_RANK_CODES: dict[int, tuple[str, int]] = {
    10: ("尊贵铂金III", _RANK_BASE["铂金"] + 4),
    11: ("尊贵铂金II", _RANK_BASE["铂金"] + 8),
    12: ("尊贵铂金I", _RANK_BASE["铂金"] + 12),
}
_LADDER: list[tuple[int, str]] = [
    (20, "永恒钻石V"),
    (21, "永恒钻石IV"),
    (13, "永恒钻石III"),
    (14, "永恒钻石II"),
    (15, "永恒钻石I"),
    (22, "至尊星耀V"),
    (23, "至尊星耀IV"),
    (24, "至尊星耀III"),
    (25, "至尊星耀II"),
    (26, "至尊星耀I"),
]
_diamond_base = _RANK_BASE["钻石"]
for _index, (_code, _label) in enumerate(_LADDER):
    _MATCH_RANK_CODES[_code] = (_label, _diamond_base + _index * 5)


def _parse_tier(name: str) -> int | None:
    for token, tier in _TIER_TOKENS:
        if token in name:
            return tier
    return None


def strip_rank_stars(rank_name: str) -> str:
    """去掉段位名末尾的「N星」。"""
    return re.sub(r"\s*\d+\s*星\s*$", "", rank_name or "").strip()


def parse_rank_score(rank_name: str | None, stars: int = 0) -> int:
    """段位名 + 星数 → 累计星数分。"""
    if not rank_name:
        return 0
    name = strip_rank_stars(rank_name)
    embedded = re.search(r"(\d+)\s*星\s*$", rank_name)
    star_count = stars if stars > 0 else (int(embedded.group(1)) if embedded else 0)

    if "王者" in name:
        return KING_BASE + max(0, star_count)

    for rank_name_key, tiers, stars_per_tier in _SUB_KING_RANKS:
        if rank_name_key not in name:
            continue
        # 小段位数字越小段位越高，识别不出时按最低小段处理。
        tier = _parse_tier(name) or tiers
        tier_index = min(max(tiers - tier, 0), tiers - 1)
        in_tier = min(max(star_count, 0), stars_per_tier)
        return _RANK_BASE[rank_name_key] + tier_index * stars_per_tier + in_tier

    return max(0, star_count)


def rank_name_from_code(code: int | None) -> str | None:
    """从历史战绩段位代码还原名称，不使用当前主页段位。

    Args:
        code: 历史战绩中的段位代码。

    Returns:
        对应的历史段位名称。
    """
    if code is None:
        return None
    if code == KING_RANK_CODE:
        return "王者"
    info = _MATCH_RANK_CODES.get(code)
    return info[0] if info else None


def rank_score_from_code(code: int | None, stars: int = 0) -> int | None:
    """对局段位代码 → 累计星数分；未知代码返回 None（调用方回退按段位名解析）。"""
    if code is None:
        return None
    if code == KING_RANK_CODE:
        return KING_BASE + max(0, stars)
    info = _MATCH_RANK_CODES.get(code)
    if info is None:
        return None
    return info[1] + min(max(stars, 0), 4 if code in {10, 11, 12} else 5)


def format_rank_label(rank_name: str | None, stars: int = 0) -> str:
    """段位展示文案，如「永恒钻石III 2星」。"""
    if not rank_name:
        return "未知"
    name = strip_rank_stars(rank_name)
    if not name:
        return f"{stars}星" if stars > 0 else "未知"
    return f"{name} {stars}星" if stars > 0 else name


def score_to_approx_label(score: int) -> str:
    """累计星数分 → 近似段位名（仅用于图表兜底展示）。"""
    if score >= KING_BASE:
        return f"王者 {score - KING_BASE}星"
    for rank_name_key, tiers, stars_per_tier in reversed(_SUB_KING_RANKS):
        base = _RANK_BASE[rank_name_key]
        if score < base:
            continue
        within = score - base
        tier = tiers - min(within // stars_per_tier, tiers - 1)
        return f"{rank_name_key}{tier}"
    return "青铜3"
