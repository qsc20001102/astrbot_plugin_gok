"""单局详情的公共展示模型，供页面和后续图片模板共同使用。"""

from __future__ import annotations

from typing import Any

from .heroes import hero_repository, strip_control_chars
from .model_utils import (
    _as_dict,
    _as_float,
    _as_int,
    _as_list,
    _first_str,
    _opt_int,
    _unwrap,
    collect_image_resources,
)

RATING_FIELDS = (
    ("sabchurthero", "输出"),
    ("sabcsurvive", "生存"),
    ("sabcKDA", "KDA"),
    ("sabcbattle", "战斗"),
    ("sabcgrow", "发育"),
)
MAX_FIELDS = (
    ("maxKill", "击杀最高"),
    ("maxHurt", "总输出最高"),
    ("maxTower", "推塔最高"),
    ("maxMoney", "经济最高"),
    ("maxHeroHurt", "对英雄伤害最高"),
    ("maxBeheroHurt", "承伤最高"),
    ("maxBehurt", "总承伤最高"),
    ("maxAssist", "助攻最高"),
    ("maxJoinGamePercent", "参团率最高"),
    ("maxCtrlTime", "控制时长最高"),
    ("maxKillSoldier", "补刀最多"),
    ("maxHealCnt", "治疗量最高"),
)


def _player_row(
    role: dict[str, Any], index: int, target_role_id: str
) -> dict[str, Any]:
    """将一个玩家规范化；缺失的补充统计保留为空，不冒充真实零值。

    Args:
        role: 营地返回的玩家对象。
        index: 队伍内的展示序号。
        target_role_id: 被查询的角色标识。

    Returns:
        与展示方式无关的玩家数据。
    """
    basic = _as_dict(role.get("basicInfo"))
    stats = _as_dict(role.get("battleStats"))
    records = _as_dict(role.get("battleRecords"))
    hero = _as_dict(records.get("usedHero")) or _as_dict(basic.get("usedHero"))
    hero_id = (
        _first_str(records, "heroId")
        or _first_str(hero, "heroId")
        or _first_str(basic, "heroId")
    )
    role_id = _first_str(basic, "roleId")
    rate = _as_float(stats.get("joinGamePercent"))
    equipment = [
        {
            "id": _first_str(item, "equipId"),
            "name": _first_str(item, "equipName"),
            "icon": _first_str(item, "equipIcon"),
        }
        for item in _as_list(records.get("finalEquips"))
        if isinstance(item, dict)
        and any(item.get(key) for key in ("equipId", "equipName", "equipIcon"))
    ]
    groups = []
    for group in _as_list(role.get("dataBehaviorV2")):
        if not isinstance(group, dict):
            continue
        items = [
            {
                "name": _first_str(item, "name"),
                "value": item.get("data"),
                "note": _first_str(item, "dataNote"),
                "note_text": f"前{item['dataNote']}"
                if isinstance(item.get("dataNote"), str)
                and item["dataNote"].endswith("%")
                and item["dataNote"][:-1].replace(".", "", 1).isdigit()
                else _first_str(item, "dataNote"),
                "highlight": bool(item.get("dataHighlight")),
                "note_highlight": bool(item.get("dataNoteHighlight")),
            }
            for item in _as_list(group.get("dataCounts"))
            if isinstance(item, dict)
            and item.get("name")
            and item.get("data") not in (None, "")
        ]
        if items:
            groups.append(
                {
                    "title": _first_str(group, "title"),
                    "icon": _first_str(group, "icon"),
                    "items": items,
                }
            )
    skill = _as_dict(records.get("skill"))
    kills = _as_int(stats.get("killCnt", stats.get("killcnt")))
    deaths = _as_int(stats.get("deadCnt", stats.get("deadcnt")))
    assists = _as_int(stats.get("assistCnt", stats.get("assistcnt")))
    # 保留旧公开字段，同时新增精确的英雄伤害与总伤害，避免两种口径混用。
    hero_damage = _opt_int(stats, "totalHeroHurtCnt")
    damage_taken = _opt_int(stats, "totalBeheroHurtCnt")
    return {
        "index": index,
        "role_id": role_id,
        "player_id": _first_str(basic, "playerId"),
        "nickname": strip_control_chars(_first_str(basic, "roleName", "nickname")),
        "hero_id": hero_id,
        "hero_name": _first_str(hero, "heroName")
        or (hero_repository.name(hero_id) if hero_id else ""),
        "hero_icon": _first_str(records, "heroIcon") or _first_str(hero, "heroIcon"),
        "avatar": _first_str(basic, "roleIcon"),
        "equipment": equipment,
        "skill": {
            "id": _first_str(skill, "skillId"),
            "name": _first_str(skill, "skillName"),
            "icon": _first_str(skill, "skillIcon"),
        },
        "image_resources": collect_image_resources(role),
        "level": _opt_int(stats, "heroLevel", "level"),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kda": round((kills + assists) / max(1, deaths), 1),
        "money": _as_int(stats.get("money")),
        "hurt": hero_damage
        if hero_damage is not None
        else _as_int(stats.get("totalHurtCnt")),
        "behurt": damage_taken
        if damage_taken is not None
        else _as_int(stats.get("totalBehurtCnt")),
        "hero_damage": hero_damage,
        "total_damage": _opt_int(stats, "totalHurtCnt"),
        "damage_taken": damage_taken,
        "total_damage_taken": _opt_int(stats, "totalBehurtCnt"),
        "tower_count": _opt_int(stats, "towerCnt"),
        "fight_power": _as_int(stats.get("fightPower")),
        "fight_power_delta": _opt_int(stats, "addFightPower"),
        "score": _as_float(stats.get("gradeGame")),
        "mvp": _as_int(stats.get("mvp")) == 1,
        "evaluate_icon": _first_str(
            stats, "evaluateIconV3", "evaluateIconV2", "evaluateIcon"
        ),
        "participation": round(rate * 100, 1)
        if rate is not None and 0 <= rate <= 1
        else None,
        "control_seconds": _as_float(stats.get("ctrlTime")),
        "minions": _opt_int(stats, "killSoldier"),
        "healing": _opt_int(stats, "healCnt"),
        "building_damage": _opt_int(stats, "buildingDamage"),
        "jungle_economy": _opt_int(stats, "monsterCoin"),
        "stats_available": bool(stats),
        "ratings": [
            {"label": label, "grade": str(stats[key]).upper()}
            for key, label in RATING_FIELDS
            if str(stats.get(key, "")).lower() in {"s", "a", "b", "c"}
        ],
        "performance": groups,
        "honors": [label for key, label in MAX_FIELDS if _as_int(stats.get(key)) == 1],
        "is_target": bool(target_role_id and role_id == target_role_id),
    }


def parse_battle_detail(payload: dict[str, Any], target_role_id: str) -> dict[str, Any]:
    """解析双方玩家和实际返回范围内的队伍汇总。

    Args:
        payload: 单局详情原始响应。
        target_role_id: 被查询角色的标识。

    Returns:
        双方数据、目标玩家表现和数据完整性说明。
    """
    data = _unwrap(payload)
    result: dict[str, Any] = {}
    head = _as_dict(data.get("head"))
    head_camp = _as_int(head.get("acntCamp"))
    outcome = head.get("gameResult")
    winning_camp = (
        head_camp
        if outcome in (True, 1, "1")
        else 3 - head_camp
        if outcome in (False, 0, "0")
        else None
    )
    if head_camp not in {1, 2}:
        winning_camp = None
    for side in ("blue", "red"):
        rows = [
            _player_row(role, index + 1, target_role_id)
            for index, role in enumerate(_as_list(data.get(f"{side}Roles")))
            if isinstance(role, dict)
        ]
        team = _as_dict(data.get(f"{side}Team"))
        expected = len(_as_list(team.get("pickHeros")))
        complete = len(rows) == expected if expected else None
        for field, legacy, percent in (
            ("hero_damage", "hurt", "hurt_percent"),
            ("damage_taken", "behurt", "behurt_percent"),
        ):
            # 占比只比较确实返回的玩家；公开完整性字段让各展示端注明统计范围。
            total = sum(row[legacy] for row in rows)
            for row in rows:
                row[percent] = round(row[legacy] / total * 100, 1) if total else None
                row[f"{field}_percent"] = (
                    round(row[field] / sum(item[field] or 0 for item in rows) * 100, 1)
                    if row[field] is not None and any(item[field] for item in rows)
                    else None
                )
        result[side] = rows
        for index, row in enumerate(rows):
            row["player_key"] = f"{side}:{index}"
            row["mvp_type"] = (
                ("mvp" if winning_camp == (1 if side == "blue" else 2) else "svp")
                if row["mvp"] and winning_camp is not None
                else ""
            )
        result[f"{side}_summary"] = {
            "players": len(rows),
            "expected_players": expected or None,
            "complete": complete,
            "kills": sum(row["kills"] for row in rows),
            "money": sum(row["money"] for row in rows),
            "hero_damage": sum(row["hero_damage"] or 0 for row in rows)
            if any(row["hero_damage"] is not None for row in rows)
            else None,
        }
    result["target"] = next(
        (row for side in ("blue", "red") for row in result[side] if row["is_target"]),
        None,
    )
    result["has_detail"] = bool(result["blue"] or result["red"])
    result["image_resources"] = collect_image_resources(data)
    result["head"] = {
        key: value
        for key, value in _as_dict(data.get("head")).items()
        if key in {"gameResult", "acntCamp", "gameTime", "usedTime", "mapName"}
    }
    return result
