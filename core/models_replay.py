"""地图回顾的公共模型；只规范化接口实际返回的轨迹与事件。"""

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
)
from .replay_protocol import (
    ECONOMY_INTERVAL_SECONDS,
    MAP_HALF_SIZE,
    MAP_IMAGE_URL,
    POSITION_INTERVAL_SECONDS,
    RESOURCE_NAMES,
    ROAD_NAMES,
    TOWER_NAMES,
    TOWER_POSITIONS,
)


def map_position(x: Any, y: Any) -> dict[str, float] | None:
    """沿用营地坐标投影，地图外坐标保留为轨迹断点。

    Args:
        x: 原始地图横坐标。
        y: 原始地图纵坐标。

    Returns:
        0～100 的地图百分比坐标；无效坐标返回空。
    """
    horizontal, vertical = _as_float(x), _as_float(y)
    if (
        horizontal is None
        or vertical is None
        or not (
            -MAP_HALF_SIZE <= horizontal <= MAP_HALF_SIZE
            and -MAP_HALF_SIZE <= vertical <= MAP_HALF_SIZE
        )
    ):
        return None
    return {
        "x": round((horizontal + MAP_HALF_SIZE) / (2 * MAP_HALF_SIZE) * 100, 4),
        "y": round((MAP_HALF_SIZE - vertical) / (2 * MAP_HALF_SIZE) * 100, 4),
    }


def _battle_summary(
    battle: dict[str, Any], by_object: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """说明交战人数、持续时间和击杀，参与英雄只通过对象 ID 关联。

    Args:
        battle: 原始交战结构。
        by_object: 对局对象 ID 到公共玩家模型的映射。

    Returns:
        可复用的交战说明与结构化摘要。
    """
    members = {1: [], 2: []}
    seen = set()
    for item in _as_list(battle.get("joinMemInfo")):
        if not isinstance(item, dict):
            continue
        object_id = _first_str(item, "objID")
        camp = _as_int(item.get("camp"))
        if (camp, object_id) in seen or camp not in members:
            continue
        seen.add((camp, object_id))
        player = by_object.get(object_id)
        if player:
            members[camp].append(
                {key: player[key] for key in ("player_id", "hero_name", "nickname")}
            )
    counts = {camp: _opt_int(battle, f"camp{camp}MemNum") for camp in (1, 2)}
    for camp in (1, 2):
        if counts[camp] is not None and counts[camp] < 0:
            counts[camp] = None
        if counts[camp] is None and isinstance(battle.get("joinMemInfo"), list):
            counts[camp] = sum(value[0] == camp for value in seen)
    kills, killed = {1: 0, 2: 0}, set()
    for item in _as_list(battle.get("killInfo")):
        if not isinstance(item, dict):
            continue
        key = (_first_str(item, "objID"), item.get("time"), item.get("killerObjID"))
        if key in killed:
            continue
        killed.add(key)
        camp = _as_int(item.get("killerCamp"))
        if camp in kills:
            kills[camp] += 1
    start, end = _as_float(battle.get("startTime")), _as_float(battle.get("endTime"))
    duration = (
        (end - start) / 1000
        if start is not None and end is not None and end >= start
        else None
    )
    names = {1: "蓝方", 2: "红方"}
    lines = [
        f"{names[camp]}参与："
        + "、".join(player["hero_name"] for player in members[camp])
        for camp in (1, 2)
        if members[camp]
    ]
    first = _as_int(battle.get("firstKillerCamp"))
    kill_data_available = isinstance(battle.get("killInfo"), list)
    if first in names and kill_data_available and sum(kills.values()):
        lines.append(f"首个击杀由{names[first]}完成")
    title = (
        f"交战 · 蓝方 {counts[1]} 人 vs 红方 {counts[2]} 人"
        if all(counts[camp] is not None for camp in (1, 2))
        else "双方交战"
    )
    description = (
        f"蓝方击杀 {kills[1]} : {kills[2]} 红方"
        if kill_data_available
        else "未返回击杀明细"
    )
    if duration is not None:
        description = f"持续 {duration:g} 秒 · {description}"
    return {
        "title": title,
        "description": description,
        "details_lines": lines,
        "fight_id": _first_str(battle, "fightId"),
        "end_time_seconds": end / 1000 if duration is not None else None,
        "duration_seconds": duration,
        "participants": {"blue": members[1], "red": members[2]},
        "participant_counts": {"blue": counts[1], "red": counts[2]},
        "kills": {
            "blue": kills[1] if kill_data_available else None,
            "red": kills[2] if kill_data_available else None,
        },
    }


def _event(
    raw: dict[str, Any], index: int, by_object: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """按官方事件结构识别时间和资源类型，未知字段不自行推断。"""
    event_type = _first_str(raw, "eventType")
    detail = _as_dict(raw.get("dtData"))
    battle = _as_dict(raw.get("battle"))
    time_ms = (
        _as_float(detail.get("killTime"))
        if detail
        else _as_float(battle.get("startTime"))
    )
    if time_ms is None:
        time_ms = _as_float(raw.get("eventTime", raw.get("startTime")))
    if time_ms is None or time_ms < 0:
        return None
    kind, title = "other", "关键事件"
    description = ""
    extra: dict[str, Any] = {}
    if event_type == "dragontower":
        object_type, object_id = (
            _as_int(detail.get("dtType"), -1),
            _as_int(detail.get("dtID"), -1),
        )
        if object_type == 2:
            # 实测同一建筑会重复返回记录，不把每条都宣称为一次摧毁。
            kind, title = "tower", "水晶事件" if object_id in {10, 20} else "防御塔事件"
        elif object_type == 1:
            kind, title = "resource", f"击败{RESOURCE_NAMES.get(object_id, '中立资源')}"
    elif event_type == "singleKill":
        kind, title = "kill", "击杀事件"
    elif event_type == "battle":
        kind = "battle"
        extra = _battle_summary(battle, by_object)
        title, description = extra.pop("title"), extra.pop("description")
    elif event_type == "killbuff":
        kind, title = "resource", "击败 buff"
    elif event_type == "highLight":
        title = "高光时刻"
    elif event_type == "equipment":
        title = "装备变化"
    position_source = detail or battle or raw
    position = map_position(position_source.get("viewX"), position_source.get("viewY"))
    if kind == "tower":
        # 实测建筑坐标常为 0/0，沿用官方塔配置定位，不把它画在河道中心。
        object_id = _as_int(detail.get("dtID"), -1)
        object_camp = _as_int(detail.get("dtCamp"), -1)
        object_name = "防御塔"
        if object_camp in {1, 2} and object_id in {10, 20}:
            object_name = "水晶"
            coordinate = (-42, -42) if object_camp == 1 else (42, 42)
            position = map_position(*coordinate)
        elif object_camp in {1, 2} and 1 <= object_id % 10 <= 9:
            road = 2 - ((object_id % 10 - 1) // 3)
            tower = {0: 0, 2: 1, 1: 2}[object_id % 10 % 3]
            object_name = ROAD_NAMES[road] + TOWER_NAMES[tower]
            position = map_position(*TOWER_POSITIONS[object_camp - 1][road][tower])
        else:
            position = None
        side = {1: "蓝方", 2: "红方"}.get(object_camp, "")
        actor = {1: "蓝方", 2: "红方"}.get(_as_int(detail.get("killerCamp")), "")
        title = (
            f"{actor}推塔 · {side}{object_name}"
            if actor
            else f"{side}{object_name}事件"
        )
        contributions = _as_list(detail.get("kills"))
        contribution_total = sum(
            max(0, _opt_int(item, "hurtTotal") or 0)
            for item in contributions
            if isinstance(item, dict)
        )
        contributors = []
        for item in contributions:
            if not isinstance(item, dict):
                continue
            player = by_object.get(_first_str(item, "killerId"))
            if player:
                hurt_total = _opt_int(item, "hurtTotal")
                contributors.append(
                    {
                        **{
                            key: player[key]
                            for key in ("player_id", "hero_name", "nickname")
                        },
                        # 回顾贡献值与详情建筑伤害的单位尚未确认，不直接展示绝对伤害。
                        "hurt_total_raw": hurt_total,
                        "contribution_percent": round(
                            hurt_total / contribution_total * 100, 1
                        )
                        if hurt_total is not None
                        and hurt_total >= 0
                        and contribution_total > 0
                        else None,
                        "camp": _as_int(item.get("camp")),
                    }
                )
        killer = by_object.get(_first_str(detail, "killerId"))
        if contributors:
            description = "参与：" + "、".join(
                dict.fromkeys(item["hero_name"] for item in contributors)
            )
        elif killer:
            description = f"参与：{killer['hero_name']}"
        else:
            description = "该记录未列出参与英雄"
        extra = {
            "object_name": object_name,
            "object_id": str(object_id),
            "object_camp": object_camp if object_camp in {1, 2} else None,
            "contributors": contributors,
            "details_lines": [
                f"{item['hero_name']} · {item['nickname']}"
                + (
                    f" · 伤害贡献 {item['contribution_percent']:g}%"
                    if item["contribution_percent"] is not None
                    else ""
                )
                for item in contributors
            ],
        }
    camp = _as_int(detail.get("killerCamp", raw.get("camp")), -1)
    return {
        "id": str(index),
        "type": kind,
        "event_type": event_type,
        "title": _first_str(raw, "title") or title,
        "description": _first_str(raw, "desc", "description") or description,
        "time_seconds": round(time_ms / 1000, 3),
        "camp": camp if camp in {1, 2} else None,
        "position": position,
        **extra,
    }


def _kill_events(
    data: dict[str, Any],
    by_object: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """将实测 killInfo 关联到玩家与死亡点，不猜测未返回的击杀者。"""
    events, seen = [], set()
    for raw in _as_list(data.get("keyEventArr")):
        if not isinstance(raw, dict):
            continue
        for kill in _as_list(_as_dict(raw.get("battle")).get("killInfo")):
            if not isinstance(kill, dict):
                continue
            milliseconds = _as_float(kill.get("time"))
            victim = by_object.get(_first_str(kill, "objID"))
            killer = by_object.get(_first_str(kill, "killerObjID"))
            if milliseconds is None or milliseconds < 0 or not victim:
                continue
            seconds = milliseconds / 1000
            key = (victim["player_id"], milliseconds, _first_str(kill, "killerObjID"))
            if key in seen:
                continue
            seen.add(key)
            death = next(
                (item for item in victim["deaths"] if item["time_seconds"] == seconds),
                None,
            )
            events.append(
                {
                    "id": f"kill-{len(events)}",
                    "type": "kill",
                    "event_type": "killInfo",
                    "title": f"{killer['hero_name']} 击败 {victim['hero_name']}"
                    if killer
                    else f"{victim['hero_name']} 被击败",
                    "description": f"{killer['nickname']} → {victim['nickname']}"
                    if killer
                    else victim["nickname"],
                    "time_seconds": seconds,
                    "camp": _as_int(kill.get("killerCamp")),
                    "position": death["position"] if death else None,
                    "killer_player_id": killer["player_id"] if killer else "",
                    "victim_player_id": victim["player_id"],
                }
            )
    return events


def _tower_states(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构造官方 5v5 塔位，并把重复推塔记录合并成一次消失时刻。

    Args:
        events: 已规范化的关键事件，时间单位为秒。

    Returns:
        双方十八座防御塔的位置与最早摧毁记录；未返回摧毁记录时刻为空。
    """
    destroyed: dict[tuple[int, int, int], float] = {}
    for event in events:
        if event.get("type") != "tower":
            continue
        camp = _as_int(event.get("object_camp"))
        object_id = _as_int(event.get("object_id"))
        seconds = _as_float(event.get("time_seconds"))
        digit = object_id % 10
        if (
            camp not in {1, 2}
            or object_id <= 0
            or not 1 <= digit <= 9
            or seconds is None
        ):
            continue
        road = 2 - ((digit - 1) // 3)
        tier = {0: 0, 2: 1, 1: 2}[digit % 3]
        key = (camp, road, tier)
        destroyed[key] = min(destroyed.get(key, seconds), seconds)
    towers = []
    for camp, roads in enumerate(TOWER_POSITIONS, 1):
        for road, positions in enumerate(roads):
            for tier, coordinate in enumerate(positions):
                towers.append(
                    {
                        "id": f"{camp}:{road}:{tier}",
                        "camp": camp,
                        "road": ROAD_NAMES[road],
                        "tier": TOWER_NAMES[tier],
                        "name": ("蓝方" if camp == 1 else "红方")
                        + ROAD_NAMES[road]
                        + TOWER_NAMES[tier],
                        "position": map_position(*coordinate),
                        "destroyed_at": destroyed.get((camp, road, tier)),
                    }
                )
    return towers


def parse_battle_replay(
    payload: dict[str, Any],
    target_player_id: str,
    duration_seconds: int = 0,
    detail_players: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """关联回顾成员、每秒轨迹、死亡点及关键事件。

    Args:
        payload: 回顾接口原始响应。
        target_player_id: 从单局详情取得的目标 playerId。
        duration_seconds: 列表返回的真实对局时长，没有则为零。
        detail_players: 同一场详情的玩家模型，用来补充回顾未返回的昵称和图片。

    Returns:
        可以直接供 WebUI 或图片渲染使用的回顾模型。
    """
    data = _unwrap(payload)
    report = _as_dict(data.get("reportData"))
    supplements = {
        row["player_id"]: row for row in (detail_players or []) if row.get("player_id")
    }
    positions = {
        _first_str(item, "playerID"): item
        for item in _as_list(report.get("playerPosInfo"))
        if isinstance(item, dict)
    }
    bases = {
        _first_str(item, "playID"): item
        for item in _as_list(data.get("playBaseInfoArr"))
        if isinstance(item, dict)
    }
    players = []
    max_trajectory_time = 0
    for member in _as_list(data.get("matchInfo")):
        if not isinstance(member, dict):
            continue
        player_id = _first_str(member, "playerId")
        if not player_id:
            continue
        supplement = supplements.get(player_id, {})
        trajectory = _as_dict(positions.get(player_id))
        points = []
        for index, point in enumerate(_as_list(trajectory.get("posArr"))):
            # 不能先删除异常点再计算时间，否则后面的所有位置都会提前。
            position = (
                map_position(point[0], point[1])
                if isinstance(point, (list, tuple)) and len(point) >= 2
                else None
            )
            points.append(
                {
                    "time_seconds": index * POSITION_INTERVAL_SECONDS,
                    "position": position,
                }
            )
        if points:
            max_trajectory_time = max(max_trajectory_time, points[-1]["time_seconds"])
        deaths = []
        for death in _as_list(_as_dict(bases.get(player_id)).get("deathPosArr")):
            if not isinstance(death, dict):
                continue
            seconds = _as_float(death.get("time"))
            position = map_position(death.get("coordX"), death.get("coordY"))
            if seconds is not None and seconds >= 0:
                deaths.append({"time_seconds": seconds, "position": position})
        revives = []
        for point in _as_list(trajectory.get("revivePosArr")):
            if not isinstance(point, (list, tuple)) or len(point) < 3:
                continue
            seconds = _as_float(point[2])
            if seconds is not None and seconds >= 0:
                revives.append(
                    {
                        "time_seconds": seconds,
                        "position": map_position(point[0], point[1]),
                    }
                )
        hero_id = _first_str(member, "heroId")
        players.append(
            {
                "player_id": player_id,
                "role_id": _first_str(member, "roleId"),
                "nickname": strip_control_chars(
                    _first_str(member, "roleName")
                    or str(supplement.get("nickname") or "")
                ),
                "hero_id": hero_id,
                "hero_name": _first_str(member, "heroName")
                or hero_repository.name(hero_id),
                "hero_icon": _first_str(member, "heroIcon")
                or str(supplement.get("hero_icon") or ""),
                "camp": _as_int(member.get("acntcamp", member.get("acntCamp"))),
                "is_target": player_id == target_player_id,
                "points": points,
                "deaths": deaths,
                "revives": revives,
                "has_revive_data": "revivePosArr" in trajectory,
            }
        )
    by_player = {player["player_id"]: player for player in players}
    by_object = {
        _first_str(base, "inBattleObjID"): by_player[player_id]
        for player_id, base in bases.items()
        if player_id in by_player and base.get("inBattleObjID") not in (None, "")
    }
    raw_events = [
        item for item in _as_list(data.get("keyEventArr")) if isinstance(item, dict)
    ]
    for group in _as_list(data.get("extendEventArr")):
        if isinstance(group, dict):
            raw_events.extend(
                item
                for item in _as_list(group.get("eventList"))
                if isinstance(item, dict)
            )
    events, seen = [], set()
    for index, raw in enumerate(raw_events):
        event = _event(raw, index, by_object)
        if event is None:
            continue
        key = (
            event["event_type"],
            event["time_seconds"],
            event["title"],
            event["camp"],
            str(event["position"]),
            event.get("fight_id"),
        )
        if key not in seen:
            seen.add(key)
            events.append(event)
    events.extend(_kill_events(data, by_object))
    events.sort(key=lambda item: item["time_seconds"])
    duration = max(
        duration_seconds,
        max_trajectory_time,
        max((event["time_seconds"] for event in events), default=0),
    )
    economy = []
    for index, value in enumerate(_as_list(data.get("ecoDistance"))):
        difference = _as_float(value)
        if difference is not None:
            economy.append(
                {
                    "time_seconds": index * ECONOMY_INTERVAL_SECONDS,
                    "difference": difference,
                }
            )
    has_trajectory = any(
        any(point["position"] for point in player["points"]) for player in players
    )
    return {
        "available": bool(has_trajectory or events),
        "has_trajectory": has_trajectory,
        "has_events": bool(events),
        "duration_seconds": duration,
        "map_image": MAP_IMAGE_URL,
        "players": players,
        "events": events,
        "towers": _tower_states(events) if has_trajectory or events else [],
        "economy": economy,
        "target_player_id": target_player_id,
        "message": ""
        if has_trajectory or events
        else "营地暂未返回这场对局的轨迹或关键事件",
    }
