"""QQ 登录、公共详情模型与地图回顾的离线回归，不访问外部服务。"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from test_plugin import install_stubs  # noqa: E402

install_stubs()
from core import camp_login  # noqa: E402
from core.camp_api import CampDataApi  # noqa: E402
from core.camp_auth import CampAccount  # noqa: E402
from core.camp_login import CampLoginManager  # noqa: E402
from core.http import HttpClient, HttpResponse  # noqa: E402
from core.login_qq import QQLoginFlow, capture_auth_code, exchange_qq_code  # noqa: E402
from core.models import parse_battle_row, parse_profile  # noqa: E402
from core.models_detail import parse_battle_detail  # noqa: E402
from core.models_replay import map_position, parse_battle_replay  # noqa: E402
from core.service import GokService  # noqa: E402
from core.sqlite import AsyncSQLiteDB  # noqa: E402
from core.storage import GokStorage  # noqa: E402
from fixtures_expansion import (  # noqa: E402
    BATTLES,
    FixtureApi,
    detail_payload,
    replay_payload,
)


class DisplayModels(unittest.TestCase):
    def test_profile_game_status_preserves_zero_and_known_codes(self):
        for raw, label in (
            (0, "离线"),
            (1, "在线"),
            (2, "游戏中"),
            ("0", "离线"),
            ("1", "在线"),
            ("2", "游戏中"),
        ):
            with self.subTest(raw=raw):
                data = parse_profile(
                    {"roleList": [{"roleId": "1", "gameOnline": raw}]}
                ).to_dict()
                self.assertEqual(data["game_online"], int(raw))
                self.assertEqual(data["game_status"], label)

    def test_profile_missing_or_invalid_game_status_is_unknown(self):
        for role in (
            {"roleId": "1"},
            *(
                {"roleId": "1", "gameOnline": value}
                for value in (None, "", 3, -1, "bad", True, False, 0.5)
            ),
        ):
            with self.subTest(role=role):
                data = parse_profile({"roleList": [role]}).to_dict()
                self.assertIsNone(data["game_online"])
                self.assertEqual(data["game_status"], "未知")

    def test_profile_game_status_uses_target_role(self):
        data = parse_profile(
            {
                "targetRoleId": "2",
                "roleList": [
                    {"roleId": "1", "gameOnline": 0},
                    {"roleId": 2, "gameOnline": 2},
                ],
            }
        ).to_dict()
        self.assertEqual(data["role_id"], "2")
        self.assertEqual(data["game_status"], "游戏中")

    def test_total_damage_taken_and_tower_count_preserve_zero_and_missing(self):
        payload = detail_payload()
        stats = payload["data"]["blueRoles"][0]["battleStats"]
        stats.update({"totalBehurtCnt": "108089", "towerCnt": 0})
        row = parse_battle_detail(payload, "111")["target"]
        self.assertEqual(row["total_damage_taken"], 108089)
        self.assertEqual(row["tower_count"], 0)
        self.assertNotEqual(row["total_damage_taken"], row["damage_taken"])
        stats.pop("totalBehurtCnt")
        stats.pop("towerCnt")
        row = parse_battle_detail(payload, "111")["target"]
        self.assertIsNone(row["total_damage_taken"])
        self.assertIsNone(row["tower_count"])

    def test_battle_summary_links_unique_participants_and_counts_kills(self):
        payload = replay_payload()
        bases = payload["data"]["playBaseInfoArr"]
        for index, object_id in ((0, "b1"), (1, "b2"), (5, "r1")):
            bases[index]["inBattleObjID"] = object_id
        kill = {
            "camp": "2",
            "objID": "r1",
            "killerCamp": "1",
            "killerObjID": "b1",
            "time": "38000",
        }
        payload["data"]["keyEventArr"] = [
            {
                "eventType": "battle",
                "battle": {
                    "startTime": "28000",
                    "endTime": "38000",
                    "firstKillerCamp": "1",
                    "joinMemInfo": [
                        {"camp": "1", "objID": "b1"},
                        {"camp": "1", "objID": "b1"},
                        {"camp": "1", "objID": "b2"},
                        {"camp": "2", "objID": "r1"},
                    ],
                    "killInfo": [kill, kill],
                },
            }
        ]
        event = next(
            item
            for item in parse_battle_replay(payload, "100")["events"]
            if item["type"] == "battle"
        )
        self.assertEqual(event["participant_counts"], {"blue": 2, "red": 1})
        self.assertEqual(event["kills"], {"blue": 1, "red": 0})
        self.assertEqual(event["duration_seconds"], 10)
        self.assertEqual(len(event["participants"]["blue"]), 2)
        self.assertIn("蓝方 2 人 vs 红方 1 人", event["title"])
        self.assertIn("持续 10 秒", event["description"])
        self.assertTrue(any("妲己" in line for line in event["details_lines"]))
        self.assertIsNone(event["position"])

    def test_battle_missing_kills_and_bad_end_time_are_not_reported_as_zero(self):
        payload = replay_payload()
        payload["data"]["keyEventArr"] = [
            {"eventType": "battle", "battle": {"startTime": "3000", "endTime": "1000"}}
        ]
        event = parse_battle_replay(payload, "100")["events"][0]
        self.assertEqual(event["kills"], {"blue": None, "red": None})
        self.assertEqual(event["participant_counts"], {"blue": None, "red": None})
        self.assertIsNone(event["duration_seconds"])
        self.assertIsNone(event["end_time_seconds"])
        self.assertIn("未返回击杀明细", event["description"])

    def test_tower_name_uses_object_camp_and_keeps_repeated_records(self):
        payload = replay_payload()
        payload["data"]["playBaseInfoArr"][0]["inBattleObjID"] = "builder"
        payload["data"]["keyEventArr"] = [
            {
                "eventType": "dragontower",
                "dtData": {
                    "dtType": "2",
                    "dtID": "18",
                    "dtCamp": "2",
                    "killTime": time,
                    "killerCamp": "1",
                    "killerId": "builder",
                    "kills": [{"killerId": "builder", "camp": "1", "hurtTotal": "700"}],
                    "viewX": 0,
                    "viewY": 0,
                },
            }
            for time in ("40000", "50000")
        ]
        events = parse_battle_replay(payload, "100")["events"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["title"], "蓝方推塔 · 红方下路二塔")
        self.assertEqual(events[0]["position"], map_position(50, 7))
        self.assertEqual(events[0]["contributors"][0]["hurt_total_raw"], 700)
        self.assertEqual(events[0]["contributors"][0]["contribution_percent"], 100)
        self.assertIn("妲己", events[0]["description"])
        self.assertTrue(
            any("伤害贡献 100%" in line for line in events[0]["details_lines"])
        )
        # 未关联到英雄的贡献记录也应进入分母，不能把已知玩家伪装成 100%。
        payload["data"]["keyEventArr"][0]["dtData"]["kills"].append(
            {"killerId": "unmatched", "camp": "1", "hurtTotal": "700"}
        )
        event = parse_battle_replay(payload, "100")["events"][0]
        self.assertEqual(event["contributors"][0]["contribution_percent"], 50)
        towers = parse_battle_replay(payload, "100")["towers"]
        self.assertEqual(len(towers), 18)
        red = next(item for item in towers if item["name"] == "红方下路二塔")
        blue = next(item for item in towers if item["name"] == "蓝方下路二塔")
        self.assertEqual(red["destroyed_at"], 40)
        self.assertEqual(red["position"], map_position(50, 7))
        self.assertIsNone(blue["destroyed_at"])

    def test_tower_timeline_preserves_zero_and_ignores_resource_events(self):
        payload = replay_payload()
        payload["data"]["keyEventArr"] = [
            {
                "eventType": "dragontower",
                "dtData": {"dtType": 2, "dtID": 11, "dtCamp": 1, "killTime": 0},
            },
            {
                "eventType": "dragontower",
                "dtData": {"dtType": 1, "dtID": 11, "dtCamp": 2, "killTime": 1000},
            },
        ]
        towers = parse_battle_replay(payload, "100")["towers"]
        self.assertEqual(
            next(item for item in towers if item["name"] == "蓝方上路一塔")[
                "destroyed_at"
            ],
            0,
        )
        self.assertEqual(sum(item["destroyed_at"] is not None for item in towers), 1)

    def test_detail_uses_true_damage_and_preserves_missing_fields(self):
        payload = detail_payload()
        stats = payload["data"]["blueRoles"][0]["battleStats"]
        stats["totalHeroHurtCnt"] = 0
        stats.pop("ctrlTime")
        stats["money"] = "非法数字"
        row = parse_battle_detail(payload, "111")["target"]
        self.assertEqual(row["hurt"], 0)
        self.assertEqual(row["total_damage"], 180000)
        self.assertIsNone(row["control_seconds"])
        self.assertEqual(row["participation"], 68.0)
        self.assertEqual(row["ratings"][0], {"label": "输出", "grade": "S"})
        self.assertEqual(row["fight_power_delta"], 36)
        self.assertEqual(row["player_id"], "100")

    def test_partial_teams_report_the_returned_scope(self):
        payload = detail_payload()
        payload["data"]["blueRoles"] = payload["data"]["blueRoles"][:2]
        detail = parse_battle_detail(payload, "111")
        self.assertFalse(detail["blue_summary"]["complete"])
        self.assertAlmostEqual(
            sum(row["hero_damage_percent"] for row in detail["blue"]), 100.0
        )
        self.assertEqual(detail["blue_summary"]["expected_players"], 5)

    def test_missing_time_and_unknown_result_are_not_fabricated(self):
        row = parse_battle_row({"heroId": 109, "usedtime": 924})
        self.assertEqual(row.duration_sec, 924)
        self.assertIsNone(row.played_at)
        self.assertEqual(row.result, "unknown")
        self.assertEqual(row.played_at_text, "时间未返回")

    def test_map_projection_and_invalid_points(self):
        self.assertEqual(map_position(-54, -54), {"x": 0.0, "y": 100.0})
        self.assertEqual(map_position(54, 54), {"x": 100.0, "y": 0.0})
        self.assertEqual(map_position(0, 0), {"x": 50.0, "y": 50.0})
        for value in (None, "nan", "inf", 100, -100):
            self.assertIsNone(map_position(value, 0))

    def test_replay_keeps_time_index_holes_and_event_units(self):
        payload = replay_payload()
        payload["data"]["reportData"]["playerPosInfo"][0]["posArr"] = [
            [0, 0],
            [100, 100],
            [2, 4],
        ]
        replay = parse_battle_replay(payload, "100", 924)
        player = next(row for row in replay["players"] if row["is_target"])
        self.assertIsNone(player["points"][1]["position"])
        self.assertEqual(player["points"][2]["time_seconds"], 2)
        self.assertEqual(player["deaths"][0]["time_seconds"], 300)
        event = next(row for row in replay["events"] if row["type"] == "tower")
        self.assertEqual(event["time_seconds"], 272)
        self.assertEqual(replay["economy"][1]["time_seconds"], 30)
        self.assertTrue(replay["has_events"])

    def test_empty_replay_is_explicitly_unavailable(self):
        replay = parse_battle_replay({"data": {}}, "missing")
        self.assertFalse(replay["available"])
        self.assertEqual(replay["events"], [])
        self.assertTrue(replay["message"])

    def test_real_kill_structure_joins_object_ids_and_death_coordinates(self):
        payload = replay_payload()
        data = payload["data"]
        data["playBaseInfoArr"][0]["inBattleObjID"] = "victim-object"
        data["playBaseInfoArr"][5]["inBattleObjID"] = "killer-object"
        kill = {
            "time": "300000",
            "objID": "victim-object",
            "killerObjID": "killer-object",
            "killerCamp": "2",
        }
        data["keyEventArr"].extend(
            [
                {
                    "eventType": "battle",
                    "battle": {"startTime": "295000", "killInfo": [kill]},
                },
                {
                    "eventType": "battle",
                    "battle": {"startTime": "299000", "killInfo": [kill]},
                },
            ]
        )
        parsed = parse_battle_replay(payload, "100", 924)
        kills = [
            event for event in parsed["events"] if event["event_type"] == "killInfo"
        ]
        self.assertEqual(len(kills), 1)
        self.assertEqual(kills[0]["time_seconds"], 300)
        self.assertEqual(kills[0]["position"], map_position(-12, 4))
        self.assertEqual(kills[0]["victim_player_id"], "100")
        self.assertEqual(kills[0]["killer_player_id"], "200")

    def test_tower_zero_coordinates_use_confirmed_map_configuration(self):
        payload = replay_payload()
        event = next(
            item
            for item in payload["data"]["keyEventArr"]
            if item["eventType"] == "dragontower"
        )
        event["dtData"].update(
            {"dtType": 2, "dtID": 11, "dtCamp": 2, "viewX": 0, "viewY": 0}
        )
        parsed = parse_battle_replay(payload, "100")
        tower = next(item for item in parsed["events"] if item["type"] == "tower")
        self.assertNotEqual(tower["position"], {"x": 50.0, "y": 50.0})
        self.assertEqual(tower["position"], map_position(-23, 49))

    def test_revive_timing_is_kept_in_seconds(self):
        payload = replay_payload()
        payload["data"]["reportData"]["playerPosInfo"][0]["revivePosArr"] = [
            [-42, -42, "320"]
        ]
        player = parse_battle_replay(payload, "100")["players"][0]
        self.assertTrue(player["has_revive_data"])
        self.assertEqual(player["revives"][0]["time_seconds"], 320)

    def test_replay_identity_is_supplemented_from_the_same_match(self):
        payload = replay_payload()
        payload["data"]["matchInfo"][0]["roleName"] = ""
        payload["data"]["matchInfo"][0]["heroIcon"] = ""
        detail = parse_battle_detail(detail_payload(), "111")
        player = parse_battle_replay(
            payload, "100", 924, detail["blue"] + detail["red"]
        )["players"][0]
        self.assertEqual(player["nickname"], "示例玩家")
        self.assertTrue(player["hero_icon"])

    def test_mvp_label_respects_the_winning_team(self):
        payload = detail_payload()
        payload["data"]["redRoles"][0]["battleStats"]["mvp"] = True
        result = parse_battle_detail(payload, "111")
        self.assertEqual(result["blue"][0]["mvp_type"], "mvp")
        self.assertEqual(result["red"][0]["mvp_type"], "svp")

    def test_ranked_zero_peak_values_are_not_a_peak_change(self):
        payload = {**BATTLES[0], "oldMasterMatchScore": 0, "newMasterMatchScore": 0}
        self.assertIsNone(parse_battle_row(payload).peak_delta)


class QQProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_callback_host_is_checked(self):
        self.assertEqual(
            capture_auth_code("auth://tauth.qq.com/?code=ABC123"), "ABC123"
        )
        self.assertEqual(
            capture_auth_code("https://tauth.qq.com/?code=ABC123"), "ABC123"
        )
        self.assertEqual(
            capture_auth_code("http://auth//tauth.qq.com/?code=ABC123"), "ABC123"
        )
        for url in (
            "auth://evil.test/?code=ABC123",
            "https://tauth.qq.com.evil.test/?code=ABC123",
            "https://openmobile.qq.com/?code=ABC123",
            "http://auth//tauth.qq.com.evil.test/?code=ABC123",
            "http://auth//tauth.qq.com/other?code=ABC123",
            "http://auth:80//tauth.qq.com/?code=ABC123",
            "http://evil.test//tauth.qq.com/?code=ABC123",
            "auth://tauth.qq.com/?code=%3Cscript%3E",
        ):
            self.assertEqual(capture_auth_code(url), "")

    async def test_ysdk_signature_matches_fixed_protocol_vector(self):
        http = Mock()
        http.request = AsyncMock(
            return_value=HttpResponse(
                200,
                text=json.dumps(
                    {
                        "code": 0,
                        "data": {
                            "ret": 0,
                            "accessToken": "platform-token",
                            "openID": "open-id",
                        },
                    }
                ),
            )
        )
        with patch("core.login_qq.time.time", return_value=1700000000):
            await exchange_qq_code(http, "TESTCODE")
        arguments = http.request.call_args.kwargs
        self.assertEqual(
            arguments["headers"]["Auth-Secret-Digest"],
            "BBLdBzYsfiAx3pZASG43iD9SnyCLlmRYN1FNojIw4I4=",
        )
        self.assertEqual(
            arguments["data"], '{"appID":"1105200115","loginCode":"TESTCODE"}'
        )
        self.assertEqual(arguments["headers"]["Content-Type"], "json")

    async def test_business_failure_is_rejected_even_with_http_200(self):
        http = Mock()
        for response in (
            {"code": 0, "data": {"ret": 1}},
            {"code": 0, "data": {"ret": 0}},
            [],
        ):
            http.request = AsyncMock(
                return_value=HttpResponse(200, text=json.dumps(response))
            )
            with self.assertRaises(ValueError):
                await exchange_qq_code(http, "TESTCODE")

    async def test_browser_cleanup_is_idempotent(self):
        flow = QQLoginFlow()
        flow._context = Mock(close=AsyncMock())
        flow._browser = Mock(close=AsyncMock())
        flow._playwright = Mock(stop=AsyncMock())
        await asyncio.gather(flow.close(), flow.close())
        flow._context.close.assert_awaited_once()
        flow._browser.close.assert_awaited_once()
        flow._playwright.stop.assert_awaited_once()


class LoginLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        camp_login._SESSIONS.clear()
        self.http = HttpClient()
        self.store = Mock(upsert=AsyncMock())
        self.manager = CampLoginManager(self.http, auth_store=self.store)

    async def asyncTearDown(self):
        await self.manager.close()
        await self.http.close()

    async def session(self):
        flow = Mock(
            start=AsyncMock(return_value=base64.b64encode(b"png").decode()),
            poll=AsyncMock(return_value={"status": "authorized", "code": "TESTCODE"}),
            close=AsyncMock(),
        )
        with patch("core.camp_login.QQLoginFlow", return_value=flow):
            session, error = await self.manager.create_session("qq")
        self.assertFalse(error)
        await session.creation_task
        return session, flow

    async def test_qr_preparation_does_not_block_the_page(self):
        gate = asyncio.Event()

        async def start(**options):
            await gate.wait()
            return "cG5n"

        flow = Mock(start=AsyncMock(side_effect=start), close=AsyncMock())
        with patch("core.camp_login.QQLoginFlow", return_value=flow):
            session, error = await self.manager.create_session("qq")
        self.assertFalse(error)
        self.assertEqual(
            (await self.manager.poll(session.task_id))["status"], "preparing"
        )
        self.manager.drop_session(session.task_id)
        await asyncio.sleep(0)
        self.assertNotIn(session.task_id, camp_login._SESSIONS)
        gate.set()

    async def test_qq_auth_is_redeemed_once_and_saved_before_success(self):
        session, flow = await self.session()
        self.store.upsert.side_effect = [OSError("disk"), None]
        account = CampAccount(user_id="123456", token="camp-token", user_key="test-key")
        with (
            patch(
                "core.camp_login.exchange_qq_code",
                new=AsyncMock(
                    return_value={"accessToken": "platform-token", "openID": "open-id"}
                ),
            ) as exchange,
            patch.object(
                self.manager,
                "_login_qq",
                new=AsyncMock(return_value={"userId": "123456", "token": "camp-token"}),
            ),
            patch.object(self.manager, "build_account", return_value=account),
        ):
            first = await self.manager.poll(session.task_id)
            second = await self.manager.poll(session.task_id)
            third = await self.manager.poll(session.task_id)
        self.assertEqual(first["status"], "error")
        self.assertFalse(first["terminal"])
        self.assertEqual(second["status"], "success")
        self.assertEqual(third["status"], "success")
        self.assertEqual(exchange.await_count, 1)
        self.assertEqual(self.store.upsert.await_count, 2)
        self.assertEqual(account.login_platform, "qq")
        self.assertFalse(
            {"token", "user_key", "encode_res", "access_token"}
            & account.public_dict().keys()
        )
        flow.close.assert_awaited()

    async def test_canceled_exchange_cannot_continue_to_login(self):
        session, _ = await self.session()
        started, release = asyncio.Event(), asyncio.Event()

        async def exchange(*args):
            started.set()
            await release.wait()
            return {"accessToken": "platform-token", "openID": "open-id"}

        with (
            patch("core.camp_login.exchange_qq_code", side_effect=exchange),
            patch.object(self.manager, "_login_qq", new=AsyncMock()) as login,
        ):
            polling = asyncio.create_task(self.manager.poll(session.task_id))
            await started.wait()
            self.manager.drop_session(session.task_id)
            release.set()
            result = await polling
        self.assertEqual(result["status"], "canceled")
        login.assert_not_awaited()
        self.store.upsert.assert_not_awaited()


class ReplayService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = AsyncSQLiteDB(Path(self.directory.name) / "gok.db")
        await self.db.connect()
        self.storage = GokStorage(self.db)
        await self.storage.initialize()
        self.api = FixtureApi()
        self.api.get_battle_replay = AsyncMock(wraps=self.api.get_battle_replay)
        self.service = GokService({}, self.storage, Mock(), self.api, Mock())

    async def asyncTearDown(self):
        await self.db.close()
        self.directory.cleanup()

    async def test_replay_uses_clicked_match_and_target_player_id(self):
        result = await self.service.battle_replay(
            "123456789", game_seq=BATTLES[3]["gameSeq"]
        )
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["data"]["match"]["game_seq"], BATTLES[3]["gameSeq"])
        self.assertEqual(
            self.api.get_battle_replay.call_args.kwargs["player_id"], "100"
        )
        self.assertEqual(
            self.api.get_battle_replay.call_args.kwargs["game_seq"],
            BATTLES[3]["gameSeq"],
        )

    async def test_missing_match_never_falls_back_to_another_game(self):
        result = await self.service.battle_replay("123456789", game_seq="removed-game")
        self.assertNotEqual(result["code"], 200)
        self.api.get_battle_replay.assert_not_awaited()

    async def test_missing_player_id_does_not_fabricate_a_replay(self):
        payload = detail_payload()
        payload["data"]["blueRoles"][0]["basicInfo"].pop("playerId")
        self.api.get_battle_detail = AsyncMock(return_value=payload)
        result = await self.service.battle_replay(
            "123456789", game_seq=BATTLES[0]["gameSeq"]
        )
        self.assertFalse(result["data"]["available"])
        self.api.get_battle_replay.assert_not_awaited()

    async def test_request_contract_uses_player_id_not_role_id(self):
        client = Mock(request=AsyncMock(return_value={"data": {}}))
        await CampDataApi(client).get_battle_replay(
            game_seq="game", game_svr="server", relay_svr="relay", player_id="player"
        )
        self.assertEqual(
            client.request.call_args.args,
            (
                "/game/battleanalyze/old",
                {
                    "gameSeq": "game",
                    "gameSvr": "server",
                    "relaySvr": "relay",
                    "playerId": "player",
                    "h5Get": 1,
                },
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
