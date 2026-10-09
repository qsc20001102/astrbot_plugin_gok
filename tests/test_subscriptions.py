"""Offline regressions for subscription polling, routing and latest-only delivery."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from test_plugin import install_stubs, request_stub  # noqa: E402

install_stubs()
from core.service import GokService  # noqa: E402
from core.sqlite import AsyncSQLiteDB  # noqa: E402
from core.storage import GokStorage  # noqa: E402
from core.subscriptions import SubscriptionService  # noqa: E402
from core.webui import WebUIService  # noqa: E402
from fixtures_expansion import BATTLES, PROFILE  # noqa: E402

SESSION = "test:GroupMessage:100"
OTHER = "test:FriendMessage:200"


class Subscriptions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = AsyncSQLiteDB(Path(self.temp.name) / "gok.db")
        await self.db.connect()
        self.local = GokStorage(self.db)
        await self.local.initialize()
        self.profile = copy.deepcopy(PROFILE)
        self.profile["data"]["roleList"][0]["gameOnline"] = 0
        self.battles = [copy.deepcopy(BATTLES[0])]
        self.api = SimpleNamespace(get_profile=AsyncMock(side_effect=lambda camp_id: self.profile), fetch_battles=AsyncMock(side_effect=lambda *args, **kwargs: {"list": self.battles}))
        self.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        self.config = {"subscriptions": {"status_poll_interval": 60, "battle_poll_interval": 120}}
        self.service = GokService(self.config, self.local, None, self.api, None)
        self.sub = SubscriptionService(self.service, self.context, self.config)
        await self.sub.storage.initialize()

    async def asyncTearDown(self):
        await self.sub.close()
        await self.db.close()
        self.temp.cleanup()

    async def watch(self, kind="battle", session=SESSION):
        await self.sub.add(kind, "123456789")
        await self.sub.save_session(session, [(kind, "123456789")])
        await self.sub.poll(kind)

    def next_match(self, number, result=1):
        row = copy.deepcopy(BATTLES[0])
        row.update(gameSeq=f"match-{number}", dtEventTime=BATTLES[0]["dtEventTime"] + number * 1200, gameresult=result)
        self.battles = [row, *self.battles]
        return row

    async def test_first_poll_establishes_baseline_without_old_notifications(self):
        await self.watch()
        self.context.send_message.assert_not_awaited()
        overview = await self.sub.overview()
        row = overview["modules"]["battle"]["targets"][0]
        self.assertEqual(row["snapshot"]["match"]["game_seq"], BATTLES[0]["gameSeq"])
        self.assertEqual(row["session_count"], 1)
        self.assertIsNotNone(row["last_poll_at"])

    async def test_only_latest_completed_match_is_sent_after_multiple_missed_matches(self):
        await self.watch()
        for number in (1, 2, 3):
            self.next_match(number)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        text = self.context.send_message.await_args.args[1].parts[0].removeprefix("text:")
        self.assertRegex(text, r"^【战绩推送】\n示例玩家-排位赛-2026-10-08 .*\n胜利\n战绩：8/2/9\n荣誉：")
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], "match-3")
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()

    async def test_send_failure_retries_only_current_latest_match_after_recovery(self):
        await self.watch()
        self.context.send_message.side_effect = RuntimeError("offline")
        self.next_match(1)
        await self.sub.poll("battle")
        self.next_match(2)
        await self.sub.poll("battle")
        self.next_match(3)
        self.context.send_message.side_effect = None
        self.context.send_message.reset_mock()
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], "match-3")
        self.assertFalse((await self.sub.storage.sessions())[0]["error"])

    async def test_query_failure_does_not_move_cursor_or_backfill_on_recovery(self):
        await self.watch()
        self.api.fetch_battles.side_effect = RuntimeError("private-data")
        self.next_match(1)
        await self.sub.poll("battle")
        self.next_match(2)
        self.api.fetch_battles.side_effect = lambda *args, **kwargs: {"list": self.battles}
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], "match-2")

    async def test_incomplete_or_ongoing_match_is_not_sent(self):
        await self.watch()
        self.next_match(1, result=0)
        await self.sub.poll("battle")
        self.context.send_message.assert_not_awaited()
        self.battles[0]["gameresult"] = 2
        await self.sub.poll("battle")
        self.assertIn("\n失败\n", self.context.send_message.await_args.args[1].parts[0])

    async def test_transient_empty_or_older_responses_do_not_reset_delivery_cursor(self):
        await self.watch()
        self.next_match(1)
        await self.sub.poll("battle")
        latest = list(self.battles)
        self.battles = []
        await self.sub.poll("battle")
        self.battles = [copy.deepcopy(BATTLES[0])]
        await self.sub.poll("battle")
        self.battles = latest
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()

    async def test_empty_history_baseline_can_notify_players_first_match(self):
        self.battles = []
        await self.watch()
        self.next_match(1)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()

    async def test_role_privacy_flag_does_not_block_visible_matches_or_new_pushes(self):
        self.profile["data"]["roleList"][0]["hideMatch"] = 1
        await self.watch()
        self.api.fetch_battles.assert_awaited_once_with("123456789", max_pages=1, max_matches=20)
        self.next_match(1)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        row = (await self.sub.storage.targets("battle"))[0]
        self.assertEqual(row["latest_key"], "match-1")
        self.assertFalse(row["error"])

    async def test_top_level_privacy_flag_does_not_skip_battle_lookup(self):
        self.profile["data"]["hideMatch"] = 1
        await self.watch()
        self.next_match(1)
        await self.sub.poll("battle")
        self.assertEqual(self.api.fetch_battles.await_count, 2)
        self.context.send_message.assert_awaited_once()

    async def test_empty_hidden_battles_keep_polling_and_recover_to_latest_only(self):
        self.profile["data"]["roleList"][0]["hideMatch"] = 1
        await self.watch()
        self.battles = []
        for _ in range(2):
            await self.sub.poll("battle")
        self.assertEqual(self.api.fetch_battles.await_count, 3)
        self.context.send_message.assert_not_awaited()
        row = (await self.sub.storage.targets("battle"))[0]
        self.assertIn("未查到营地战绩", row["error"])
        self.assertEqual(row["session_count"], 1)
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], BATTLES[0]["gameSeq"])
        for number in (1, 2, 3):
            self.next_match(number)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], "match-3")
        self.assertFalse((await self.sub.storage.targets("battle"))[0]["error"])

    async def test_first_empty_lookup_marks_missing_data_and_still_checks_future_matches(self):
        self.profile["data"]["roleList"][0]["hideMatch"] = 1
        self.battles = []
        await self.watch()
        row = (await self.sub.storage.targets("battle"))[0]
        self.assertIn("未查到营地战绩", row["error"])
        self.next_match(1)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()

    async def test_status_only_pushes_zero_to_one_or_two_and_reverse(self):
        await self.watch("status")
        role = self.profile["data"]["roleList"][0]
        for value in (1, 2, 1, 0, 2, 0):
            role["gameOnline"] = value
            await self.sub.poll("status")
        texts = [call.args[1].parts[0].removeprefix("text:") for call in self.context.send_message.await_args_list]
        self.assertEqual(len(texts), 4)
        self.assertTrue(texts[0].startswith("【上线推送】\n游戏昵称：示例玩家\n时间："))
        self.assertTrue(texts[1].startswith("【离线推送】\n游戏昵称：示例玩家\n时间："))
        self.assertRegex(texts[0], r"时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n上线段位：")
        self.assertRegex(texts[1], r"时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n离线段位：")

    async def test_unknown_status_or_network_error_never_becomes_offline(self):
        self.profile["data"]["roleList"][0]["gameOnline"] = 1
        await self.watch("status")
        self.profile["data"]["roleList"][0].pop("gameOnline")
        await self.sub.poll("status")
        self.api.get_profile.side_effect = RuntimeError("upstream")
        await self.sub.poll("status")
        self.context.send_message.assert_not_awaited()
        self.api.get_profile.side_effect = lambda *args: self.profile
        self.profile["data"]["roleList"][0]["gameOnline"] = 0
        await self.sub.poll("status")
        self.assertIn("【离线推送】", self.context.send_message.await_args.args[1].parts[0])

    async def test_failed_status_is_not_replayed_during_one_two_changes(self):
        await self.watch("status")
        self.context.send_message.side_effect = RuntimeError("offline")
        self.profile["data"]["roleList"][0]["gameOnline"] = 1
        await self.sub.poll("status")
        self.context.send_message.side_effect = None
        self.profile["data"]["roleList"][0]["gameOnline"] = 2
        await self.sub.poll("status")
        self.context.send_message.assert_awaited_once()

    async def test_two_sessions_share_query_but_have_independent_delivery_results(self):
        await self.watch()
        await self.sub.save_session(OTHER, [("battle", "123456789")])
        await self.sub.poll("battle")
        self.api.fetch_battles.reset_mock()
        self.next_match(1)

        async def send(session_id, chain):
            if session_id == SESSION:
                raise RuntimeError("offline")
            return True

        self.context.send_message.side_effect = send
        await self.sub.poll("battle")
        self.api.fetch_battles.assert_awaited_once()
        rows = {row["session_id"]: row for row in await self.sub.storage.links("battle", "123456789")}
        self.assertEqual(rows[OTHER]["last_key"], "match-1")
        self.assertEqual(rows[SESSION]["last_key"], BATTLES[0]["gameSeq"])

    async def test_unreferenced_targets_do_not_query_and_removing_last_session_pauses(self):
        await self.sub.add("status", "123456789")
        await self.sub.poll("status")
        self.api.get_profile.assert_not_awaited()
        await self.sub.save_session(SESSION, [("status", "123456789")])
        await self.sub.poll("status")
        await self.sub.remove_session(SESSION)
        self.api.get_profile.reset_mock()
        await self.sub.poll("status")
        self.api.get_profile.assert_not_awaited()
        overview = await self.sub.overview()
        self.assertEqual(overview["modules"]["status"]["active_count"], 0)
        self.assertIsNone(overview["modules"]["status"]["next_poll_at"])

    async def test_reactivated_session_baselines_and_does_not_push_paused_history(self):
        await self.watch()
        await self.sub.save_session(SESSION, [])
        self.next_match(1)
        self.next_match(2)
        await self.sub.save_session(SESSION, [("battle", "123456789")])
        await self.sub.poll("battle")
        self.context.send_message.assert_not_awaited()
        self.next_match(3)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()

    async def test_unlink_during_stagger_skips_the_next_upstream_request(self):
        await self.sub.add("status", "123456789")
        await self.sub.add("status", "987654321")
        await self.sub.save_session(SESSION, [("status", "123456789"), ("status", "987654321")])
        poll = asyncio.create_task(self.sub.poll("status"))
        await asyncio.sleep(0.05)
        await self.sub.unsubscribe("987654321", SESSION, "status")
        await poll
        self.api.get_profile.assert_awaited_once_with("123456789")

    async def test_restart_persists_cursors_and_only_sends_latest_new_match(self):
        await self.watch()
        self.next_match(1)
        await self.sub.poll("battle")
        await self.db.close()
        await self.db.connect()
        self.sub = SubscriptionService(self.service, self.context, self.config)
        await self.sub.storage.initialize()
        self.context.send_message.reset_mock()
        await self.sub.poll("battle")
        self.context.send_message.assert_not_awaited()
        self.next_match(2)
        self.next_match(3)
        await self.sub.poll("battle")
        self.context.send_message.assert_awaited_once()
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], "match-3")

    async def test_routing_replacement_preserves_existing_cursors_and_cascades_target_deletion(self):
        await self.watch()
        await self.sub.add("status", "123456789")
        await self.sub.save_session(SESSION, [("status", "123456789"), ("battle", "123456789")])
        rows = {row["kind"]: row for row in await self.db.fetch_all("SELECT * FROM push_links")}
        self.assertIsNone(rows["status"]["last_key"])
        self.assertEqual(rows["battle"]["last_key"], BATTLES[0]["gameSeq"])
        await self.sub.remove_target("battle", "123456789")
        self.assertFalse(await self.sub.storage.links("battle", "123456789"))
        self.assertEqual(len(await self.sub.storage.links("status", "123456789")), 1)

    async def test_invalid_routing_rolls_back_and_false_send_result_is_not_success(self):
        await self.watch()
        with self.assertRaises(ValueError):
            await self.sub.save_session(SESSION, [("status", "99999")])
        self.assertEqual(len(await self.sub.storage.links("battle", "123456789")), 1)
        self.next_match(1)
        self.context.send_message.return_value = False
        await self.sub.poll("battle")
        self.assertEqual((await self.sub.storage.links("battle", "123456789"))[0]["last_key"], BATTLES[0]["gameSeq"])
        self.assertTrue((await self.sub.storage.sessions())[0]["error"])

    async def test_current_chat_cancel_isolated_and_concurrent_subscribe_does_not_lose_links(self):
        await asyncio.gather(self.sub.subscribe("status", "123456789", SESSION), self.sub.subscribe("battle", "123456789", SESSION))
        self.assertEqual(len((await self.sub.storage.sessions())[0]["subscriptions"]), 2)
        await self.sub.save_session(OTHER, [("battle", "123456789")])
        await self.sub.unsubscribe("123456789", SESSION, "battle")
        self.assertEqual((await self.sub.list_session(SESSION))["data"].count("123456789"), 1)
        self.assertEqual(len(await self.sub.storage.links("battle", "123456789")), 1)

    async def test_schedulers_display_times_and_shutdown_without_leaking_tasks(self):
        await self.sub.add("status", "123456789")
        await self.sub.initialize()
        await asyncio.sleep(0.02)
        self.api.get_profile.assert_not_awaited()
        await self.sub.save_session(SESSION, [("status", "123456789")])
        for _ in range(100):
            overview = await self.sub.overview()
            if overview["modules"]["status"]["next_poll_at"]:
                break
            await asyncio.sleep(0.01)
        state = overview["modules"]["status"]
        self.assertIsNotNone(state["last_poll_at"])
        self.assertGreater(state["next_poll_at"], state["last_poll_at"])
        self.config["subscriptions"]["status_poll_interval"] = 30
        self.assertEqual(self.sub.interval("status"), 30)
        self.config["subscriptions"]["status_poll_interval"] = 0
        self.assertEqual(self.sub.interval("status"), 60)
        tasks = tuple(self.sub._tasks)
        await self.sub.close()
        self.assertTrue(all(task.cancelled() for task in tasks))

    async def test_web_routes_validate_inputs_and_return_module_and_session_data(self):
        web = WebUIService(self.service, subscriptions=self.sub)
        for payload in ({"action": "other"}, {"action": "add_target", "kind": "status", "camp_id": "abc"}, {"action": "save_session", "session_id": "100"}, {"action": "save_session", "session_id": SESSION, "status_ids": [12345]}):
            request_stub.set_json(payload)
            self.assertEqual((await web.subscriptions_update()).status_code, 400)
        request_stub.set_json({"action": "add_target", "kind": "status", "camp_id": "123456789"})
        self.assertEqual((await web.subscriptions_update()).status_code, 200)
        request_stub.set_json({"action": "save_session", "session_id": SESSION, "status_ids": ["123456789"], "battle_ids": []})
        data = json.loads((await web.subscriptions_update()).body)["data"]
        self.assertEqual(data["modules"]["status"]["active_count"], 1)
        self.assertEqual(data["sessions"][0]["session_id"], SESSION)
        request_stub.set_json({"action": "delete_session", "session_id": SESSION})
        self.assertEqual((await web.subscriptions_update()).status_code, 200)
        self.assertEqual(json.loads((await web.subscriptions_list()).body)["data"]["modules"]["status"]["active_count"], 0)
        self.assertEqual((await WebUIService(self.service).subscriptions_list()).status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
