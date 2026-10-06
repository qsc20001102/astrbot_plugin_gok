"""核心层离线自测：加密、段位、模型解析、本地存储。

运行：python tests/test_core.py
不依赖 AstrBot 运行时，不访问外部网络；HTTP 分块验证使用本机服务。
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import camp_crypto, xxtea  # noqa: E402
from core.heroes import hero_repository  # noqa: E402
from core.models import (  # noqa: E402
    build_battle_comment,
    parse_battle_row,
    parse_honors,
    parse_profile,
    parse_season_stats,
)
from core.rank import (  # noqa: E402
    format_rank_label,
    parse_rank_score,
    rank_name_from_code,
    rank_score_from_code,
)
from core.sqlite import AsyncSQLiteDB  # noqa: E402
from core.storage import GokStorage  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label} {detail}".strip())
        print(f"  FAIL  {label} {detail}")


# --------------------------------------------------------------------- 加密
def test_xxtea() -> None:
    print("\n[XXTEA]")
    # 与 Node 参考实现（xxtea.ts）逐字节一致的向量
    expected = "aa5j+xu3P/isV8EhjawkkUJkzcakB0gzkW28+PFJyRj7V5uAPAF6js11MBT0XJ4nSTS9IYk2D9BXGycn505DFkEWYu8="
    key = b"a8f5f167f44f4964e6c998dee827110c"
    plain = b'{"timestamp":1700000000000,"nonce":"123:aabbcc:1700000000000"}'
    actual = base64.b64encode(xxtea.encrypt(plain, key)).decode()
    check("XXTEA 与 Node 参考实现一致", actual == expected, f"\n    got={actual}")

    for size in (1, 4, 9, 16, 33, 100, 200):
        payload = bytes([65 + (i % 26) for i in range(size)])
        restored = xxtea.decrypt(xxtea.encrypt(payload, key), key)
        check(f"XXTEA 往返 len={size}", restored == payload)


def test_crypto() -> None:
    print("\n[RSA / encodeParam]")
    payload = json.dumps({"userKey": "abc", "x": "y" * 200}).encode()
    encrypted = camp_crypto.rsa_encrypt_chunked(payload)
    # 1024 位密钥：137 字节应分成 2 块
    check("RSA 分块加密长度正确", len(encrypted) == 256, f"got={len(encrypted)}")

    special = camp_crypto.build_special_encode_param()
    check("specialEncodeParam 可生成", bool(special) and len(special) > 100)

    encode_param = camp_crypto.build_encode_param("123456", "user-key-abc")
    decrypted = xxtea.decrypt(base64.b64decode(encode_param), b"user-key-abc")
    parsed = json.loads(decrypted.decode())
    check(
        "encodeParam 可用 userKey 解回", parsed.get("nonce", "").startswith("123456:")
    )
    check(
        "无 userKey 时 encodeParam 为空", camp_crypto.build_encode_param("1", "") == ""
    )


# --------------------------------------------------------------------- 段位
def test_rank() -> None:
    print("\n[段位换算]")
    check("青铜III 0星 = 0", parse_rank_score("青铜III", 0) == 0)
    check("白银III 0星 = 9", parse_rank_score("白银III", 0) == 9)
    check("黄金IV 0星 = 18", parse_rank_score("黄金IV", 0) == 18)
    check("钻石V 0星 = 50", parse_rank_score("永恒钻石V", 0) == 50)
    check("星耀I 满星 = 100", parse_rank_score("至尊星耀I", 5) == 100)
    check("王者 10星 = 110", parse_rank_score("最强王者", 10) == 110)
    check("段位名去星展示", format_rank_label("永恒钻石III", 2) == "永恒钻石III 2星")
    check("roleJob 20 -> 永恒钻石V", rank_name_from_code(20) == "永恒钻石V")
    check("roleJob 16 -> 王者", rank_name_from_code(16) == "王者")
    for code, name in ((10, "尊贵铂金III"), (11, "尊贵铂金II"), (12, "尊贵铂金I")):
        check(f"历史铂金代码 {code} -> {name}", rank_name_from_code(code) == name)
    check(
        "铂金I4星积分与钻石V1星只差一星",
        rank_score_from_code(20, 1) - rank_score_from_code(12, 4) == 1,
    )
    check("roleJob 22 5星 = 80", rank_score_from_code(22, 5) == 80)
    check("roleJob 16 3星 = 103", rank_score_from_code(16, 3) == 103)


# --------------------------------------------------------------------- 英雄
def test_heroes() -> None:
    print("\n[英雄目录]")
    check(
        "英雄目录已加载", hero_repository.count > 100, f"count={hero_repository.count}"
    )
    check("105 -> 廉颇", hero_repository.name(105) == "廉颇")
    check("未知 ID 回退", hero_repository.name(999999) == "英雄999999")
    # roles 与 branchEvaluate 编码不同，前者 4=发育路
    check("公孙离分路 = 发育路", hero_repository.role_name(199) == "发育路")


# --------------------------------------------------------------------- 模型
SAMPLE_BATTLE = {
    "gameSeq": "1234567890",
    "dtEventTime": 1700000000,
    "mapName": "排位赛",
    "gameresult": 1,
    "heroId": 107,
    "killcnt": 8,
    "deadcnt": 2,
    "assistcnt": 10,
    "gradeGame": 12.3,
    "usedTime": 935,
    "roleJob": 22,
    "stars": 5,
    "AcntCamp": 1,
    "newMasterMatchScore": 1500,
    "oldMasterMatchScore": 1480,
    "mvpUrlV3": "https://x/mvp.png",
    "evaluateUrlV3": "https://x/5142af35177e111837efbf85071f373b.png",
    "desc": "MVP",
    "gameSvrId": "svr1",
    "relaySvrId": "relay1",
    "battleType": 1,
    "hurtTotal": 90000,
    "economy": 12000,
}

SAMPLE_PROFILE = {
    "returnCode": 0,
    "data": {
        "targetRoleId": "111",
        "targetUserId": "222",
        "head": {
            "mods": [
                {
                    "modId": 701,
                    "name": "最强王者",
                    "param1": json.dumps({"rankingStar": 12}),
                }
            ]
        },
        "roleList": [
            {
                "roleId": "111",
                "roleName": "测试玩家",
                "roleIcon": "https://x/a.png",
                "areaName": "微信区",
                "serverName": "微信389区",
                "hideMatch": 1,
            }
        ],
    },
}

SAMPLE_SEASON = {
    "returnCode": 0,
    "data": {
        "historyList": [
            {
                "seasonName": "S42",
                "rankInfo": {
                    "totalCnt": 120,
                    "totalWinCnt": 66,
                    "goldCnt": 9,
                    "averageScore": 88.4,
                    "heros": [
                        {
                            "heroId": 312,
                            "heroName": "沈梦溪",
                            "heroIcon": "https://x/shen.jpg",
                            "winRate": 1,
                            "winCnt": 8,
                            "gameCnt": 8,
                            "heroFightPower": 6200,
                        }
                    ],
                },
                "masterInfo": {
                    "averageScore": 92.1,
                    "masterScore": 1523,
                    "totalCnt": 40,
                },
            }
        ],
        "headCard": {"x": 1},
    },
}


def test_models() -> None:
    print("\n[数据模型]")
    match = parse_battle_row(SAMPLE_BATTLE)
    check("对局模式 = ranked", match.mode == "ranked")
    check("对局英雄名解析", match.hero_name == "赵云", match.hero_name)
    check("对局胜负 = win", match.win)
    for code, label, stars in (
        (20, "永恒钻石V", 1),
        (12, "尊贵铂金I", 4),
        (11, "尊贵铂金II", 3),
        (10, "尊贵铂金III", 4),
    ):
        record = parse_battle_row(
            dict(SAMPLE_BATTLE, roleJob=code, roleJobName="永恒钻石V", stars=stars)
        )
        check(
            f"回填当前钻石名字不会覆盖历史{label}",
            record.rank_name == label and record.stars == stars,
        )
    unknown = parse_battle_row(
        dict(SAMPLE_BATTLE, roleJob=999, roleJobName="永恒钻石V")
    )
    check("未知历史编号不拿当前段位冒充", unknown.rank_name == "")
    check("对局 KDA", match.kda == 9.0, str(match.kda))
    check("对局时长文案", match.duration_text == "15:35", match.duration_text)
    check("roleJob 22 -> 段位名", match.rank_name == "至尊星耀V", match.rank_name)
    check("MVP 识别", match.mvp_type == "mvp", match.mvp_type)
    check("金牌打野奖牌识别", match.medal == "金牌打野", match.medal)
    check("阵营 = blue", match.side == "blue")
    check("巅峰分变化", match.peak_score == 1500 and match.peak_delta == 20)
    check("时间戳解析", match.played_at.year == 2023, str(match.played_at))

    profile = parse_profile(SAMPLE_PROFILE, "222")
    check("昵称解析", profile.nickname == "测试玩家", profile.nickname)
    check("段位名去星", profile.current_rank == "最强王者", profile.current_rank)
    check("星数解析", profile.current_stars == 12, str(profile.current_stars))
    ranked_payload = json.loads(json.dumps(SAMPLE_PROFILE))
    ranked_payload["data"]["head"]["mods"] = [
        {"modId": 708, "name": "荣耀黄金IV", "icon": "https://camp.test/wrong.png"},
        {
            "modId": 701,
            "name": "永恒钻石V",
            "icon": "https://camp.qq.com/battle/profile/roleJobV2/20.png",
            "param1": json.dumps(
                {
                    "rankingStar": "1",
                    "starImg": "https://camp.qq.com/battle/profile/starsV5/5-1.png",
                }
            ),
        },
    ]
    ranked = parse_profile(ranked_payload, "489048724").to_dict()
    check(
        "段位图使用5v5模块而非10v10模块",
        ranked["rank_icon"].endswith("/20.png")
        and ranked["rank_stars_icon"].endswith("/5-1.png")
        and ranked["current_stars"] == 1,
    )
    check("区服 = wechat", profile.area == "wechat")
    check("roleId 解析", profile.role_id == "111")
    check("服务器名解析", profile.server_name == "微信389区", profile.server_name)
    check("hideMatch 识别", profile.hide_match is True)
    check(
        "未隐藏时 hide_match 为 False",
        parse_profile(
            {"data": {"roleList": [{"roleId": "1", "roleName": "n"}]}}
        ).hide_match
        is False,
    )

    season = parse_season_stats(SAMPLE_SEASON)
    check("赛季场次", season is not None and season.season_games == 120)
    check("赛季胜场", season is not None and season.season_wins == 66)
    check("赛季金牌", season is not None and season.gold_count == 9)
    check("巅峰分", season is not None and season.peak_score == 1523)
    check("赛季名", season is not None and season.season_name == "S42")
    check("赛季英雄统计条数", season is not None and len(season.heroes) == 1)
    check(
        "赛季英雄胜率换算",
        season is not None and season.heroes[0]["win_rate"] == 100.0,
    )
    check(
        "赛季英雄战力",
        season is not None and season.heroes[0]["fight_power"] == 6200,
    )
    check("空赛季页返回 None", parse_season_stats({"data": {}}) is None)

    # 没打过巅峰赛时不应伪造 1200 分
    no_peak = parse_season_stats(
        {
            "data": {
                "historyList": [
                    {
                        "rankInfo": {"totalCnt": 5, "totalWinCnt": 3},
                        "masterInfo": {"masterScore": 0, "totalCnt": 0},
                    }
                ]
            }
        }
    )
    check("未参与巅峰时不返回分数", no_peak is not None and no_peak.peak_score is None)
    in_peak = parse_season_stats(
        {
            "data": {
                "historyList": [
                    {
                        "rankInfo": {"totalCnt": 5, "totalWinCnt": 3},
                        "masterInfo": {"masterScore": 0, "totalCnt": 7},
                    }
                ]
            }
        }
    )
    check(
        "参与巅峰但分数为 0 时用 1200 兜底",
        in_peak is not None and in_peak.peak_score == 1200,
    )

    # SVP 与旧式奖牌文件名回退
    svp = parse_honors({"mvpUrlV3": "https://x/svp.png", "desc": ""})
    check("SVP 识别", svp["mvp_type"] == "svp")
    legacy = parse_honors(
        {"evaluateUrl": "https://x/silver_shooter.png", "branchEvaluate": 3}
    )
    check("旧式奖牌回退 = 银牌发育路", legacy["medal"] == "银牌发育路", legacy["medal"])

    comment = build_battle_comment([match])
    check(
        "锐评数据字段完整", comment[0]["killcnt"] == 8 and comment[0]["gameresult"] == 1
    )


# --------------------------------------------------------------------- 存储
async def test_storage() -> None:
    print("\n[本地存储]")
    with tempfile.TemporaryDirectory() as tmp:
        db = AsyncSQLiteDB(Path(tmp) / "test.db")
        await db.connect()
        storage = GokStorage(db)
        await storage.initialize()

        check("新增别名", await storage.add_alias(123456789, "小明"))
        check("重复别名被拒绝", not await storage.add_alias(123456789, "小明2"))
        check("别名解析（按名字）", await storage.resolve_gokid("小明") == 123456789)
        check(
            "别名解析（按 ID）", await storage.resolve_gokid("987654321") == 987654321
        )
        check("别名解析（模糊）", await storage.resolve_gokid("小") == 123456789)
        check("别名解析（不存在）", await storage.resolve_gokid("不存在的人") is None)
        check("修改别名", await storage.update_alias(123456789, "小红"))
        check("修改后名称生效", await storage.resolve_gokid("小红") == 123456789)

        check("删除别名", await storage.delete_alias(123456789))
        check("删除后不可解析", await storage.resolve_gokid("小红") is None)
        check("别名计数", await storage.count_aliases() == 0)
        await db.close()


async def test_no_cache_schema() -> None:
    """确认本地库不再保留任何数据缓存表，且旧版缓存表会被清理。"""
    print("\n[无缓存设计]")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "legacy.db"
        db = AsyncSQLiteDB(db_path)
        await db.connect()

        # 伪造旧版缓存表，验证 initialize 会清理掉
        await db.execute(
            "CREATE TABLE players (camp_id TEXT PRIMARY KEY, nickname TEXT)"
        )
        await db.execute(
            "CREATE TABLE matches (external_id TEXT PRIMARY KEY, camp_id TEXT)"
        )
        await db.execute(
            "INSERT INTO players (camp_id, nickname) VALUES ('1','旧数据')"
        )

        storage = GokStorage(db)
        await storage.initialize()

        tables = {
            str(row["name"])
            for row in await db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        check("players 缓存表已清理", "players" not in tables, str(sorted(tables)))
        check("matches 缓存表已清理", "matches" not in tables, str(sorted(tables)))
        check("aliases 表保留", "aliases" in tables, str(sorted(tables)))

        check("新增别名仍可用", await storage.add_alias(123456789, "小明"))
        check("别名可读回", await storage.count_aliases() == 1)

        # 确认 GokStorage 不再暴露任何缓存读写接口
        for removed in (
            "save_player",
            "get_player",
            "save_matches",
            "get_matches",
            "hero_stats",
            "get_season_heroes",
            "count_matches",
            "get_known_external_ids",
            "clear_player",
            "stats",
        ):
            check(f"已移除缓存接口 {removed}", not hasattr(storage, removed))
        await db.close()


async def test_login_sessions() -> None:
    """扫码会话必须跨插件实例共享，否则插件重载/页面刷新会让用户看到「已过期」。"""
    print("\n[扫码会话]")
    from core import camp_login
    from core.camp_login import CampLoginManager, CampLoginSession
    from core.http import HttpClient

    camp_login._SESSIONS.clear()
    manager_a = CampLoginManager(HttpClient())
    manager_b = CampLoginManager(HttpClient())

    check("初始没有活动会话", camp_login.active_sessions() == [])

    unknown = await manager_a.poll("不存在的任务")
    check("未知会话返回 expired", unknown["status"] == "expired")
    check(
        "未知会话提示的是会话丢失而非二维码过期",
        "会话" in unknown["message"] and "重新获取" in unknown["message"],
        unknown["message"],
    )

    now = time.time()
    session = CampLoginSession(
        task_id="shared-task",
        x_log_uid="UID",
        uuid="uuid",
        qrcode_base64="/9j/4AAQ",
        created_at=now,
        expires_at=now + 60,
    )
    camp_login._SESSIONS[session.task_id] = session

    check("新实例能看到已有会话", manager_b.get_session("shared-task") is not None)
    check("活动会话列表可见", len(camp_login.active_sessions()) == 1)
    check("会话图片类型识别为 JPEG", session.qrcode_mime == "image/jpeg")

    # 过期的会话应被清理，并给出准确提示
    session.expires_at = time.time() - 1
    expired = await manager_b.poll("shared-task")
    check("过期会话返回 expired", expired["status"] == "expired")
    check("过期提示指向二维码", "二维码" in expired["message"], expired["message"])
    check("过期会话已被清理", camp_login.active_sessions() == [])

    await manager_a.http.close()
    await manager_b.http.close()
    camp_login._SESSIONS.clear()


async def test_login_completion() -> None:
    """Verify concurrent completion, retries, and deletion of saved logins."""
    print("\n[登录完成与重试]")
    from core import camp_login
    from core.camp_auth import CampAccount, CampAuthStore
    from core.camp_login import CampLoginManager, CampLoginSession
    from core.http import HttpClient

    with tempfile.TemporaryDirectory() as tmp:
        store = CampAuthStore(Path(tmp) / "camp_auth.json")
        manager = CampLoginManager(HttpClient(), auth_store=store)
        now = time.time()
        session = CampLoginSession("complete", "UID", "uuid", "/9j/", now, now + 60)
        camp_login._SESSIONS[session.task_id] = session
        account = CampAccount(
            user_id="489048724", token="test-token", user_key="test-key"
        )

        async def delayed_poll(_uuid):
            await asyncio.sleep(0.01)
            session.expires_at = time.time() - 1
            manager.list_sessions()
            check(
                "临近过期的处理中会话不会被清理",
                manager.get_session("complete") is session,
            )
            return {"wx_errcode": 405, "wx_code": "single-use-code"}

        with (
            patch.object(
                manager, "_poll_wechat", AsyncMock(side_effect=delayed_poll)
            ) as wx_poll,
            patch.object(
                manager,
                "_login_with_code",
                AsyncMock(return_value=({"userId": account.user_id}, "")),
            ) as redeem,
            patch.object(manager, "build_account", Mock(return_value=account)),
            patch.object(store, "upsert", AsyncMock(wraps=store.upsert)) as save,
        ):
            results = await asyncio.gather(
                manager.poll("complete"), manager.poll("complete")
            )
            check("并发轮询均返回成功", all(r["status"] == "success" for r in results))
            check(
                "微信轮询和换票各一次", wx_poll.await_count == redeem.await_count == 1
            )
            check(
                "返回成功前只保存一次登录态",
                save.await_count == 1
                and (await store.get(account.user_id)) is not None,
            )
            check("完成后不再恢复为活动扫码会话", manager.list_sessions() == [])
            check(
                "重复轮询不误报过期",
                (await manager.poll("complete"))["status"] == "success",
            )
            await store.remove(account.user_id)
            await manager.poll("complete")
            check(
                "重复轮询不会恢复已删除账号", await store.get(account.user_id) is None
            )

        retry = CampLoginSession("retry-save", "UID", "uuid", "/9j/", now, now + 60)
        camp_login._SESSIONS[retry.task_id] = retry
        with (
            patch.object(
                manager,
                "_poll_wechat",
                AsyncMock(return_value={"wx_errcode": 405, "wx_code": "code"}),
            ),
            patch.object(
                manager,
                "_login_with_code",
                AsyncMock(return_value=({"userId": account.user_id}, "")),
            ) as redeem,
            patch.object(manager, "build_account", Mock(return_value=account)),
            patch.object(
                store,
                "upsert",
                AsyncMock(side_effect=[OSError("disk failure"), account]),
            ),
        ):
            failed = await manager.poll(retry.task_id)
            check(
                "保存失败返回可重试错误",
                failed["status"] == "error" and not failed.get("terminal"),
            )
            check(
                "保存重试可完成登录",
                (await manager.poll(retry.task_id))["status"] == "success",
            )
            check("保存失败不重复兑换微信票据", redeem.await_count == 1)

        failed_session = CampLoginSession(
            "failed-login", "UID", "uuid", "/9j/", now, now + 60
        )
        camp_login._SESSIONS[failed_session.task_id] = failed_session
        with (
            patch.object(
                manager,
                "_poll_wechat",
                AsyncMock(return_value={"wx_errcode": 405, "wx_code": "code"}),
            ),
            patch.object(
                manager,
                "_login_with_code",
                AsyncMock(return_value=(None, "营地换票失败")),
            ),
        ):
            failure = await manager.poll(failed_session.task_id)
            replay = await manager.poll(failed_session.task_id)
            check(
                "换票失败保留实际原因",
                failure["message"] == replay["message"] == "营地换票失败",
            )
            check(
                "换票失败结束轮询而非报过期",
                replay["status"] == "error" and replay["terminal"],
            )

        canceled = CampLoginSession("canceled", "UID", "uuid", "/9j/", now, now + 60)
        camp_login._SESSIONS[canceled.task_id] = canceled

        async def cancel_during_poll(_uuid):
            manager.drop_session(canceled.task_id)
            return {"wx_errcode": 405, "wx_code": "code"}

        with (
            patch.object(
                manager, "_poll_wechat", AsyncMock(side_effect=cancel_during_poll)
            ),
            patch.object(manager, "_login_with_code", AsyncMock()) as redeem,
        ):
            check(
                "取消后忽略迟到扫码确认",
                (await manager.poll(canceled.task_id))["status"] == "canceled"
                and redeem.await_count == 0,
            )

        store.path.write_text(
            json.dumps({"accounts": [{"user_id": "incomplete", "nickname": "旧账号"}]}),
            encoding="utf-8",
        )
        check(
            "不完整账号仍可显示并删除",
            (await store.list_accounts())[0].ready is False
            and await store.remove("incomplete"),
        )
        with patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
            try:
                await store.clear()
            except OSError:
                check("清空写入失败不会被吞掉", True)
            else:
                check("清空写入失败不会被吞掉", False)
        await manager.http.close()
        camp_login._SESSIONS.clear()


async def test_live_reads() -> None:
    """Verify fresh data is fetched for repeated player and template reads."""
    print("\n[实时读取]")
    from core.camp_api import CampDataApi
    from core.service import GokService
    from core.template import TemplateRepository

    with tempfile.TemporaryDirectory() as tmp:
        db = AsyncSQLiteDB(Path(tmp) / "aliases.db")
        await db.connect()
        storage = GokStorage(db)
        await storage.initialize()
        api = Mock()
        api.get_profile = AsyncMock(return_value=SAMPLE_PROFILE)
        api.get_season_page = AsyncMock(return_value={"data": {}})
        api.fetch_battles = AsyncMock(
            side_effect=[
                {"list": [dict(SAMPLE_BATTLE, killcnt=1)]},
                {"list": [dict(SAMPLE_BATTLE, killcnt=9)]},
            ]
        )
        service = GokService({}, storage, Mock(), api, Mock())
        first = await service.battle_report("489048724")
        second = await service.battle_report("489048724")
        check(
            "同一ID重复查询拿到新战绩",
            first["data"]["list"][0]["kills"] == 1
            and second["data"]["list"][0]["kills"] == 9,
        )
        check(
            "资料和战绩每次都请求上游",
            api.get_profile.await_count == api.fetch_battles.await_count == 2,
        )
        await db.close()

        client = Mock()
        client.request = AsyncMock(
            side_effect=[
                {
                    "data": {
                        "list": [{"gameSeq": "1"}],
                        "hasMore": True,
                        "lastTime": "cursor",
                    }
                },
                {
                    "data": {
                        "list": [{"gameSeq": "1"}, {"gameSeq": "2"}],
                        "hasMore": False,
                    }
                },
                {"data": {"list": [{"gameSeq": "3"}], "hasMore": False}},
            ]
        )
        paged = CampDataApi(client)
        matches = await paged.fetch_battles("489048724", page_delay=0)
        fresh = await paged.fetch_battles("489048724", page_delay=0)
        check(
            "实时翻页保留游标并去重",
            [r["gameSeq"] for r in matches["list"]] == ["1", "2"]
            and client.request.await_args_list[1].args[1]["lastTime"] == "cursor",
        )
        check(
            "下一次查询从最新页开始",
            fresh["list"][0]["gameSeq"] == "3"
            and client.request.await_args_list[2].args[1]["lastTime"] == 0,
        )

        template = Path(tmp) / "test.html"
        template.write_text("first", encoding="utf-8")
        repository = TemplateRepository(Path(tmp))
        first_template = await repository.get("test.html")
        template.write_text("second", encoding="utf-8")
        check(
            "模板读取也不缓存",
            first_template == "first" and await repository.get("test.html") == "second",
        )


async def test_http_streaming() -> None:
    """Verify full HTTP bodies are consumed across delayed network chunks.

    Returns:
        None. Records regression results in the suite counters.
    """
    print("\n[HTTP 分块响应]")
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from core.camp_auth import CampAccount, CampAuthStore
    from core.camp_client import CampApiError, CampClient
    from core.http import HttpClient, HttpResponse

    body = json.dumps({"returnCode": 0, "data": {"padding": "x" * 50000}})

    async def streamed_response(request):
        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        await response.write(body[:13742].encode())
        await asyncio.sleep(0.02)
        await response.write(body[13742:].encode())
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/stream", streamed_response)
    http = HttpClient()
    try:
        async with TestServer(app) as server:
            result = await http.request("GET", str(server.make_url("/stream")))
            check(
                "延迟分块响应被完整读取",
                result.text == body and result.json()["data"]["padding"] == "x" * 50000,
            )
            with patch("core.http.MAX_BODY_BYTES", 14000):
                oversized = await http.request("GET", str(server.make_url("/stream")))
                check(
                    "响应上限按所有分块累计",
                    oversized.status is None and "大小限制" in oversized.error,
                )
    finally:
        await http.close()

    account = CampAccount(user_id="test", token="test-token", user_key="test-key")
    for response in (
        HttpResponse(200, text='{"returnCode":0,"data":'),
        HttpResponse(200, headers={"campencrypt": "true"}, text="invalid-base64!"),
    ):
        try:
            CampClient._parse_response(response, account)
        except CampApiError as error:
            check(
                "异常响应不会误判登录失效",
                error.code == "upstream" and not error.retryable,
            )
        else:
            check("异常响应不会误判登录失效", False)
    with tempfile.TemporaryDirectory() as tmp:
        store = CampAuthStore(Path(tmp) / "camp_auth.json")
        await store.upsert(account)
        client = CampClient(Mock(), store)
        with patch.object(
            client,
            "_request_once",
            AsyncMock(side_effect=CampApiError("坏响应", "upstream")),
        ):
            try:
                await client.request("/game/seasonpage", {})
            except CampApiError:
                saved = await store.get(account.user_id)
                check("上游响应失败不会冷却有效账号", saved.available())


async def test_account_validation() -> None:
    """Verify checks use each account's credentials and preserve login races.

    Returns:
        None. Records assertions in the suite counters.
    """
    print("\n[全部登录态检测]")
    from core.camp_auth import CampAccount, CampAuthStore
    from core.camp_client import CampClient
    from core.http import HttpResponse

    with tempfile.TemporaryDirectory() as tmp:
        store = CampAuthStore(Path(tmp) / "auth.json")
        accounts = [
            CampAccount(user_id=name, token=f"{name}-token", user_key="test-key")
            for name in ("valid", "invalid", "limited", "network")
        ]
        for account in accounts:
            await store.upsert(account)
        raw = {
            "accounts": [a.to_dict() for a in accounts] + [{"user_id": "incomplete"}]
        }
        store.path.write_text(json.dumps(raw), encoding="utf-8")
        checked_ids = []

        async def fake_request(_method, _url, *, headers, json_body):
            checked_ids.append(headers["userid"])
            check(
                "检测请求使用对应账号的 token 和目标ID",
                headers["token"] == f"{headers['userid']}-token"
                and json_body["targetUserId"] == headers["userid"],
            )
            if headers["userid"] == "network":
                return HttpResponse(None, error="请求超时")
            if headers["userid"] == "invalid":
                return HttpResponse(
                    200, text=json.dumps({"returnCode": -1, "returnMsg": "登录态失效"})
                )
            if headers["userid"] == "limited":
                return HttpResponse(
                    200,
                    text=json.dumps({"returnCode": -30107, "returnMsg": "操作频繁"}),
                )
            return HttpResponse(200, text=json.dumps({"returnCode": 0, "data": {}}))

        http = Mock()
        http.request = AsyncMock(side_effect=fake_request)
        client = CampClient(http, store)
        with patch.object(
            client,
            "request",
            AsyncMock(side_effect=AssertionError("must not use account pool")),
        ):
            result = await client.validate_accounts()
        check(
            "逐一检测全部账号且不换号掩盖失败",
            checked_ids == ["valid", "invalid", "limited", "network"]
            and result["checked"] == 5,
        )
        check(
            "有效/失效/未知分类正确",
            (result["valid"], result["invalid"], result["uncertain"]) == (1, 2, 2),
        )
        check(
            "检测结果不包含登录凭证",
            all(a.token not in json.dumps(result) for a in accounts),
        )
        invalid = await store.get("invalid")
        check(
            "已失效账号不会被账号池复用",
            invalid.auth_invalid and not invalid.available(time.time() + 10000),
        )
        check(
            "频控账号保持登录信息并进入冷却", (await store.get("limited")).is_cooled()
        )
        check("网络错误不会判定登录失效", not (await store.get("network")).auth_invalid)
        await store.record_validation(invalid, "error", "网络错误")
        check(
            "未知结果不会重新启用已失效账号", (await store.get("invalid")).auth_invalid
        )
        await store.record_validation(invalid, "valid", "登录态有效")
        check("再次验证有效可恢复使用", (await store.get("invalid")).available())

        old = await store.get("valid")
        await store.upsert(
            CampAccount(user_id="valid", token="new-token", user_key="new-key")
        )
        applied = await store.record_validation(old, "invalid", "旧 token 失效")
        check(
            "旧凭证检测不会覆盖重新登录的账号",
            not applied and not (await store.get("valid")).auth_invalid,
        )
        await store.remove("network")
        applied = await store.record_validation(accounts[3], "valid", "有效")
        check(
            "检测不会恢复已删除账号", not applied and await store.get("network") is None
        )


async def test_name_mapping_and_match_identity() -> None:
    """Verify automatic names, legacy migration, and clicked-match identity.

    Returns:
        None. Records assertions in the suite counters.
    """
    print("\n[自动角色名称和点击对局]")
    from core.camp_client import CampApiError
    from core.models import collect_image_resources
    from core.service import GokService

    with tempfile.TemporaryDirectory() as tmp:
        db = AsyncSQLiteDB(Path(tmp) / "legacy.db")
        await db.connect()
        await db.execute(
            "CREATE TABLE aliases (gokid INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)"
        )
        await db.execute("INSERT INTO aliases VALUES (123456789,'旧别名',1,2)")
        storage = GokStorage(db)
        await storage.initialize()
        await storage.initialize()
        await storage.remember_player(123456789, "游戏真名")
        row = (await storage.list_aliases())[0]
        check(
            "旧名称表迁移保留用户名字和创建时间",
            row["name"] == "旧别名"
            and row["role_name"] == "游戏真名"
            and row["created_at"] == 1,
        )
        await storage.remember_player(489048724, "角色旧名")
        await storage.remember_player(489048724, "角色新名")
        check(
            "自动记录可更新游戏改名",
            await storage.resolve_gokid("角色新名") == 489048724,
        )
        await storage.update_alias(489048724, "管理页名字")
        await storage.remember_player(489048724, "再次游戏改名")
        row = (await storage.find_aliases("再次游戏改名"))[0]
        check(
            "管理员名称不会被自动查询覆盖",
            row["name"] == "管理页名字" and row["role_name"] == "再次游戏改名",
        )
        await storage.delete_alias(489048724)

        api = Mock()
        api.get_profile = AsyncMock(return_value=SAMPLE_PROFILE)
        api.get_season_page = AsyncMock(return_value={"data": {}})
        api.fetch_battles = AsyncMock(
            return_value={
                "list": [dict(SAMPLE_BATTLE, gameSeq="new-match"), SAMPLE_BATTLE]
            }
        )
        api.get_battle_detail = AsyncMock(
            return_value={
                "data": {
                    "blueRoles": [
                        {
                            "basicInfo": {"roleId": "111", "roleName": "测试玩家"},
                            "battleStats": {"killCnt": 8, "totalHeroHurtCnt": 100},
                        }
                    ]
                }
            }
        )
        service = GokService({}, storage, Mock(), api, Mock())
        result = await service.battle_detail(
            "489048724", 1, game_seq=SAMPLE_BATTLE["gameSeq"]
        )
        check(
            "点击对局通过标识定位而不依赖旧序号",
            result["code"] == 200
            and result["data"]["index"] == 2
            and api.get_battle_detail.await_args.kwargs["game_seq"]
            == SAMPLE_BATTLE["gameSeq"],
        )
        check(
            "详情不伪造缺失等级并显示团队占比",
            result["data"]["blue"][0]["level"] is None
            and result["data"]["blue"][0]["hurt_percent"] == 100,
        )
        check(
            "成功ID查询自动保存游戏角色名称",
            (await storage.find_aliases("489048724"))[0]["role_name"] == "测试玩家",
        )
        calls = api.get_battle_detail.await_count
        missing = await service.battle_detail("489048724", 1, game_seq="missing")
        check(
            "消失对局不会回退到另一场",
            missing["code"] != 200 and api.get_battle_detail.await_count == calls,
        )
        api.fetch_battles = AsyncMock(side_effect=CampApiError("请求失败", "upstream"))
        failed = await service.battle_report("555666777")
        check(
            "失败查询不生成名称映射",
            failed["code"] != 200 and not await storage.find_aliases("555666777"),
        )
        api.get_profile = AsyncMock(return_value=SAMPLE_PROFILE)
        await service.player_overview("555666777")
        check(
            "资料成功也自动保存名称映射", bool(await storage.find_aliases("555666777"))
        )
        await storage.remember_player(222333444, "同名角色")
        await storage.remember_player(333444555, "同名角色")
        calls = api.get_profile.await_count
        ambiguous = await service.player_overview("同名角色")
        check(
            "同名角色要求使用ID而不擅自选择玩家",
            ambiguous["code"] != 200
            and "多个角色" in ambiguous["msg"]
            and api.get_profile.await_count == calls,
        )
        await db.close()

    images = collect_image_resources(
        {
            "roleIcon": "https://cdn.test/role",
            "nested": [
                {"heroIcon": "https://cdn.test/hero.png"},
                {"mvpUrlV3": "https://cdn.test/mvp.png"},
                {"detailUrl": "https://camp.test/page"},
            ],
            "duplicate": "https://cdn.test/hero.png",
            "avatar": "javascript:alert(1)",
            "token": "secret",
        }
    )
    check(
        "保留原始图片链接并去重且不提取普通页面或凭证",
        {r["url"] for r in images}
        == {
            "https://cdn.test/role",
            "https://cdn.test/hero.png",
            "https://cdn.test/mvp.png",
        },
    )
    battle = parse_battle_row(dict(SAMPLE_BATTLE, heroIcon="https://cdn.test/hero.png"))
    check(
        "战绩公开模型包含对局标识和图片",
        battle.to_dict()["game_seq"] == SAMPLE_BATTLE["gameSeq"]
        and battle.to_dict()["hero_icon"] == "https://cdn.test/hero.png"
        and len(battle.to_dict()["image_resources"]) >= 1,
    )


def main() -> int:
    test_xxtea()
    test_crypto()
    test_rank()
    test_heroes()
    test_models()
    asyncio.run(test_storage())
    asyncio.run(test_no_cache_schema())
    asyncio.run(test_login_sessions())
    asyncio.run(test_login_completion())
    asyncio.run(test_live_reads())
    asyncio.run(test_http_streaming())
    asyncio.run(test_account_validation())
    asyncio.run(test_name_mapping_and_match_identity())
    test_equipment_fields()

    print("\n" + "=" * 60)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    return 1 if FAILED else 0


def test_equipment_fields() -> None:
    """Verify confirmed Camp equipment and hero-level fields stay per player.

    Returns:
        None. Records assertions in the suite counters.
    """
    from core.service import _parse_battle_detail

    result = _parse_battle_detail(
        {
            "data": {
                "blueRoles": [
                    {
                        "basicInfo": {"roleId": "1", "roleName": "游走玩家"},
                        "battleStats": {"heroLevel": 15, "level": 0},
                        "battleRecords": {
                            "usedHero": {
                                "heroId": 525,
                                "heroIcon": "https://camp.test/hero.jpg",
                            },
                            "finalEquips": [
                                {
                                    "equipId": 1724,
                                    "equipName": "近卫·救赎",
                                    "equipIcon": "https://camp.test/1724.png",
                                },
                                {
                                    "equipId": 1336,
                                    "equipName": "极寒风暴",
                                    "equipIcon": "https://camp.test/1336.png",
                                },
                            ],
                            "skill": {
                                "skillId": 80115,
                                "skillName": "闪现",
                                "skillIcon": "https://camp.test/flash.png",
                            },
                        },
                    },
                    {
                        "basicInfo": {"roleId": "2", "roleName": "打野玩家"},
                        "battleStats": {"heroLevel": 13},
                        "battleRecords": {
                            "finalEquips": [
                                {
                                    "equipId": 1523,
                                    "equipName": "追击刀锋",
                                    "equipIcon": "https://camp.test/1523.png",
                                }
                            ]
                        },
                    },
                ],
                "redRoles": [],
            }
        },
        "1",
    )
    first, second = result["blue"]
    check(
        "装备按营地返回顺序对应各玩家",
        [item["id"] for item in first["equipment"]] == ["1724", "1336"]
        and second["equipment"][0]["name"] == "追击刀锋",
    )
    check(
        "装备图片和名称直接使用返回字段",
        first["equipment"][1]
        == {"id": "1336", "name": "极寒风暴", "icon": "https://camp.test/1336.png"},
    )
    check(
        "英雄等级优先使用真实heroLevel字段",
        first["level"] == 15 and second["level"] == 13,
    )
    check(
        "召唤师技能保留营地图片和名称",
        first["skill"]["name"] == "闪现"
        and first["skill"]["icon"] == "https://camp.test/flash.png",
    )


if __name__ == "__main__":
    sys.exit(main())
