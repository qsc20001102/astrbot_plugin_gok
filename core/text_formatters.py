"""指令文本输出：复用公共模型，以简明文字保留查询身份和关键统计。"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def _number(value: Any, suffix: str = "") -> str:
    """保留真实零值与缺失值，统一整数和一位小数的展示。

    Args:
        value: 公共模型中的统计值。
        suffix: 仅在值有效时追加的单位。

    Returns:
        带千分位的数字文本；缺失或无效值为破折号。
    """
    if value in (None, ""):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:,.1f}".rstrip("0").rstrip(".") + suffix


def _identity(profile: dict[str, Any], title: str) -> list[str]:
    """三类查询共用身份行，营地 ID 原样展示，不按数值格式化。

    Args:
        profile: 统一的玩家资料模型。
        title: 当前查询的标题。

    Returns:
        包含查询标题、昵称、营地 ID、区服和段位的两行文字。
    """
    rank = str(profile.get("rank_label") or "")
    region = profile.get("server_name") or profile.get("area_name") or ""
    parts = [f"ID {profile.get('camp_id') or '—'}"]
    if region:
        parts.append(str(region))
    if rank and rank != "未知":
        parts.append(f"{rank} {_number(profile.get('current_stars'), '星')}")
    return [f"{title}｜{profile.get('nickname') or '未知角色'}", " · ".join(parts)]


def _profile(data: dict[str, Any]) -> str:
    """生成资料摘要，常用英雄最多展示三个。

    Args:
        data: 资料查询返回的统一模型。

    Returns:
        身份、赛季统计、评分及常用英雄的简明文字。
    """
    profile = data.get("profile") or {}
    lines = _identity(profile, "资料")
    if profile.get("season_games", 0) > 0:
        lines.append(
            f"赛季 {_number(profile['season_games'])}场 / {_number(profile.get('season_wins'))}胜"
            f" · 胜率 {_number(profile.get('win_rate'), '%')}"
        )
    else:
        lines.append("赛季：暂无统计")
    lines.append(
        f"排位评分 {_number(profile.get('rank_score') or None)}"
        f" · 巅峰积分 {_number(profile.get('peak_score') or None)}"
    )
    heroes = data.get("season_heroes") or []
    if heroes:
        lines.append(
            "常用："
            + "；".join(
                f"{hero.get('hero_name') or '未知英雄'} {_number(hero.get('games'))}场 {_number(hero.get('win_rate'), '%')}"
                for hero in heroes[:3]
            )
        )
    if data.get("hide_match") or profile.get("hide_match"):
        lines.append("战绩已隐藏")
    return "\n".join(lines)


def _battle(data: dict[str, Any]) -> str:
    """按每场一行生成战绩，保留序号用于查询单局。

    Args:
        data: 战绩查询返回的统一模型。

    Returns:
        查询身份、统计摘要和对局列表的简明文字。
    """
    lines = _identity(
        data.get("profile") or {}, str(data.get("query_title") or "全部战绩")
    )
    summary = data.get("summary") or {}
    rows = data.get("list") or []
    lines.append(
        f"近 {_number(summary.get('total', len(rows)))} 场 · 胜率 {_number(summary.get('win_rate'), '%')}"
        f" · 均分 {_number(summary.get('avg_score') or None)}"
    )
    year = str(datetime.now(ZoneInfo("Asia/Shanghai")).year)
    for index, match in enumerate(rows, 1):
        outcome = {"win": "胜", "lose": "负"}.get(match.get("result"), "—")
        score = _number(match.get("score") or None)
        honors = []
        if match.get("mvp_type") in {"mvp", "svp"}:
            honors.append(str(match["mvp_type"]).upper())
        if match.get("medal"):
            honors.append(str(match["medal"]))
        honor = " · ".join(honors)
        played_at = str(match.get("played_at") or "时间—")
        if played_at.startswith(f"{year}-"):
            played_at = played_at[5:]
        lines.append(
            f"{index}. {played_at} {outcome} · {match.get('hero_name') or '未知英雄'}"
            f" {match.get('kills', 0)}/{match.get('deaths', 0)}/{match.get('assists', 0)}"
            f" · {score}分" + (f" · {honor}" if honor else "")
        )
    if summary.get("total", len(rows)) != len(rows):
        lines.append(f"展示 {len(rows)} 场")
    return "\n".join(lines)


def _detail(data: dict[str, Any]) -> str:
    """生成双方阵容摘要，省略图片中才需要的装备和伤害明细。

    Args:
        data: 单局查询返回的统一模型。

    Returns:
        比赛信息、双方总览和每位玩家 KDA、评分的简明文字。
    """
    lines = _identity(data.get("profile") or {}, "对局")
    match = data.get("match") or {}
    played_at = str(match.get("played_at") or "时间—")
    year = str(datetime.now(ZoneInfo("Asia/Shanghai")).year)
    if played_at.startswith(f"{year}-"):
        played_at = played_at[5:]
    lines.append(
        " · ".join(
            str(value)
            for value in (
                played_at,
                match.get("mode_name"),
                match.get("result_text"),
                match.get("duration_text"),
            )
            if value
        )
    )
    for side, title in (("blue", "蓝方"), ("red", "红方")):
        summary = data.get(f"{side}_summary") or {}
        heading = (
            f"{title} · {_number(summary.get('kills'))}击杀 · {_number(summary.get('money'))}经济"
            if summary
            else title
        )
        lines.append(heading)
        for player in data.get(side) or []:
            score = _number(player.get("score"))
            honor = (
                str(player.get("mvp_type") or "").upper() if player.get("mvp") else ""
            )
            lines.append(
                f"{player.get('nickname') or '未知玩家'} · {player.get('hero_name') or '未知英雄'}"
                f" {player.get('kills', 0)}/{player.get('deaths', 0)}/{player.get('assists', 0)}"
                f" · {score}分" + (f" {honor}" if honor else "")
            )
    if not data.get("blue") and not data.get("red"):
        lines.append("玩家详情暂未返回")
    return "\n".join(lines)


def format_service_text(result: dict[str, Any]) -> str:
    """按结果模板选择简明文本，错误和业务已有的文本原样保留。

    Args:
        result: 服务层返回的 code / msg / data / temp。

    Returns:
        可直接发送到聊天的文字，不含图片渲染细节。
    """
    if result.get("code") != 200:
        return str(result.get("msg") or "查询失败")
    data = result.get("data")
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return "查询完成"
    if data.get("text"):
        return str(data["text"])
    template = result.get("temp")
    if template == "aliases.html":
        rows = data.get("list") or []
        lines = [f"角色（{len(rows)}）", "游戏昵称 | 营地ID | 别名"]
        lines.extend(
            f"{row.get('role_name') or '待更新昵称'} | {row.get('gokid') or '—'} | {row.get('alias') or '—'}"
            for row in rows
        )
        return "\n".join(lines)
    formatter = {
        "profile.html": _profile,
        "battle.html": _battle,
        "detail.html": _detail,
    }.get(template)
    return formatter(data) if formatter else "查询完成"
