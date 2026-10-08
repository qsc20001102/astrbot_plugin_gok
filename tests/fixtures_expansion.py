"""新增功能的合成响应，仅用于离线测试，不包含真实玩家或账号凭据。"""

from __future__ import annotations

import copy
import math
from datetime import datetime
from zoneinfo import ZoneInfo

PROFILE = {
    "returnCode": 0,
    "data": {
        "targetRoleId": "111",
        "targetUserId": "123456789",
        "head": {
            "mods": [
                {"modId": 701, "name": "王者", "param1": '{"rankingStar":24}'},
                {"modId": 702, "content": "1680"},
            ]
        },
        "roleList": [
            {
                "roleId": "111",
                "roleName": "示例玩家",
                "roleIcon": "https://game.gtimg.cn/images/yxzj/img201606/heroimg/109/109.jpg",
                "areaName": "微信区",
                "serverName": "微信389区",
                "hideMatch": 0,
            }
        ],
    },
}
SEASON = {
    "returnCode": 0,
    "data": {
        "historyList": [
            {
                "seasonId": 47,
                "seasonName": "示例赛季",
                "rankInfo": {
                    "totalCnt": 120,
                    "totalWinCnt": 72,
                    "averageScore": 88.5,
                    "goldCnt": 21,
                    "heros": [
                        {
                            "heroId": 109,
                            "heroName": "妲己",
                            "heroIcon": "https://game.gtimg.cn/images/yxzj/img201606/heroimg/109/109.jpg",
                            "gameCnt": 30,
                            "winCnt": 18,
                            "winRate": 0.6,
                            "heroFightPower": 5200,
                        }
                    ],
                },
                "masterInfo": {
                    "totalCnt": 40,
                    "masterScore": 1680,
                    "averageScore": 89.2,
                },
            }
        ]
    },
}
BATTLES = [
    {
        "gameSeq": str(100001 + index),
        "dtEventTime": int(
            datetime(2026, 10, 8, 20, 14, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        )
        - index * 1320,
        "mapName": "巅峰赛" if index % 3 == 1 else "排位赛",
        "gameresult": 2 if index % 3 == 1 else 1,
        "heroId": [109, 199, 167][index % 3],
        "heroIcon": f"https://game.gtimg.cn/images/yxzj/img201606/heroimg/{[109, 199, 167][index % 3]}/{[109, 199, 167][index % 3]}.jpg",
        "killcnt": 8 + index % 4,
        "deadcnt": 2 + index % 3,
        "assistcnt": 9,
        "gradeGame": 12.1 - index % 4,
        "usedtime": 924 + index * 12,
        "roleJob": 16,
        "stars": 24,
        "AcntCamp": 1,
        "mvpcnt": 1 if index % 3 == 0 else 0,
        "gameSvrId": "svr-test",
        "relaySvrId": "relay-test",
        "battleType": 32,
    }
    for index in range(10)
]


def detail_payload() -> dict:
    """生成字段完整的 5v5 响应，并为目标玩家保留回顾标识。"""
    data = {
        "head": {"acntCamp": 1, "gameResult": 1},
        "blueTeam": {"pickHeros": [109, 199, 167, 105, 312]},
        "redTeam": {"pickHeros": [109, 199, 167, 105, 312]},
    }
    for side, camp in (("blue", 1), ("red", 2)):
        rows = []
        for index, hero_id in enumerate((109, 199, 167, 105, 312)):
            role_id = "111" if camp == 1 and index == 0 else str(camp * 1000 + index)
            rows.append(
                {
                    "basicInfo": {
                        "roleId": role_id,
                        "playerId": str(camp * 100 + index),
                        "roleName": "示例玩家"
                        if role_id == "111"
                        else f"示例队员{camp}-{index + 1}",
                        "isMe": role_id == "111",
                    },
                    "battleStats": {
                        "heroLevel": 15 - index % 2,
                        "killCnt": 8 - index,
                        "deadCnt": 2 + index,
                        "assistCnt": 9 + index,
                        "money": 13000 - index * 800,
                        "gradeGame": 12.1 - index * 0.7,
                        "totalHeroHurtCnt": 96000 - index * 14000,
                        "totalHurtCnt": 180000 - index * 16000,
                        "totalBeheroHurtCnt": 78000 + index * 12000,
                        "fightPower": 5200,
                        "addFightPower": 36 if role_id == "111" else 0,
                        "joinGamePercent": 0.68,
                        "ctrlTime": 22.4,
                        "killSoldier": 118,
                        "mvp": 1 if role_id == "111" else 0,
                        "sabchurthero": "s",
                        "sabcsurvive": "a",
                        "sabcKDA": "s",
                        "sabcbattle": "a",
                        "sabcgrow": "a",
                        "maxHeroHurt": 1 if index == 0 else 0,
                    },
                    "battleRecords": {
                        "usedHero": {
                            "heroId": hero_id,
                            "heroName": {
                                109: "妲己",
                                199: "公孙离",
                                167: "孙悟空",
                                105: "廉颇",
                                312: "沈梦溪",
                            }[hero_id],
                            "heroIcon": f"https://game.gtimg.cn/images/yxzj/img201606/heroimg/{hero_id}/{hero_id}.jpg",
                        },
                        "finalEquips": [
                            {
                                "equipId": item,
                                "equipName": f"示例装备{item}",
                                "equipIcon": f"https://game.gtimg.cn/images/yxzj/img201606/itemimg/{item}.jpg",
                            }
                            for item in (1422, 1136, 1232, 1238, 1231, 1235)
                        ],
                        "skill": {},
                    },
                    "dataBehaviorV2": [
                        {
                            "title": "分路表现",
                            "dataCounts": [
                                {
                                    "name": "对位经济差",
                                    "data": "+1320",
                                    "dataNote": "前 12%",
                                    "dataHighlight": True,
                                },
                                {
                                    "name": "支援参与",
                                    "data": "6 次",
                                    "dataNote": "前 20%",
                                },
                            ],
                        },
                        {
                            "title": "团队贡献",
                            "dataCounts": [
                                {
                                    "name": "伤害贡献",
                                    "data": "28.5%",
                                    "dataNote": "前 8%",
                                }
                            ],
                        },
                    ],
                }
            )
        data[f"{side}Roles"] = rows
    return {"returnCode": 0, "data": data}


def replay_payload() -> dict:
    """按官方确认的协议生成模拟轨迹和毫秒事件时间。"""
    data = {
        "matchInfo": [],
        "playBaseInfoArr": [],
        "reportData": {"playerPosInfo": []},
        "ecoDistance": [index * 100 - 700 for index in range(31)],
        "keyEventArr": [],
    }
    detail = detail_payload()["data"]
    for camp, side in ((1, "blue"), (2, "red")):
        for index, row in enumerate(detail[f"{side}Roles"]):
            basic, hero = row["basicInfo"], row["battleRecords"]["usedHero"]
            player_id = basic["playerId"]
            data["matchInfo"].append(
                {
                    "playerId": player_id,
                    "roleId": basic["roleId"],
                    "roleName": basic["roleName"],
                    "acntcamp": camp,
                    **hero,
                }
            )
            points = [
                [
                    round(
                        -42
                        + min(second, 700) / 700 * 72
                        + math.sin(second / 45 + index) * 4,
                        2,
                    ),
                    round(
                        -40
                        + min(second, 700) / 700 * 60
                        + math.cos(second / 60 + index) * 5,
                        2,
                    ),
                ]
                for second in range(925)
            ]
            data["reportData"]["playerPosInfo"].append(
                {"playerID": player_id, "posArr": points}
            )
            data["playBaseInfoArr"].append(
                {
                    "playID": player_id,
                    "acntCamp": camp,
                    "deathPosArr": [
                        {
                            "time": 300 + index * 12,
                            "coordX": -12 + index,
                            "coordY": 4 + index,
                        }
                    ],
                }
            )
    for time_ms, object_type, object_id, x, y in (
        (272000, 2, 11, -5, 22),
        (370000, 1, 9, 18, -23),
        (665000, 2, 24, 8, 12),
        (820000, 1, 8, -19, 23),
    ):
        data["keyEventArr"].append(
            {
                "eventType": "dragontower",
                "dtData": {
                    "dtType": object_type,
                    "dtID": object_id,
                    "killTime": time_ms,
                    "killerCamp": 1,
                    "dtCamp": 2,
                    "viewX": x,
                    "viewY": y,
                },
            }
        )
    data["keyEventArr"].extend(
        [
            {
                "eventType": "singleKill",
                "battle": {"startTime": 126000, "viewX": -30, "viewY": -16},
            },
            {
                "eventType": "battle",
                "battle": {"startTime": 512000, "viewX": 5, "viewY": 14},
            },
        ]
    )
    return {"returnCode": 0, "data": data}


class FixtureApi:
    """只在离线测试和外部预览进程使用的响应提供者。"""

    async def get_profile(self, camp_id):
        result = copy.deepcopy(PROFILE)
        result["data"]["targetUserId"] = str(camp_id)
        return result

    async def get_season_page(self, role_id):
        return copy.deepcopy(SEASON)

    async def fetch_battles(self, camp_id, **options):
        option = options.get("option", 0)
        rows = copy.deepcopy(BATTLES)
        if option:
            rows = [row for row in rows if ("巅峰" in row["mapName"]) == (option == 4)]
        return {"list": rows, "pages": 1, "has_more": False}

    async def get_battle_detail(self, **options):
        return detail_payload()

    async def get_battle_replay(self, **options):
        return replay_payload()

    async def search_users(self, nickname):
        return [
            {
                "uid": "123456789",
                "name": nickname,
                "region": "微信区",
                "dw": "王者",
                "avatar": "",
            },
            {
                "uid": "123456788",
                "name": nickname,
                "region": "QQ区",
                "dw": "星耀",
                "avatar": "",
            },
        ]
