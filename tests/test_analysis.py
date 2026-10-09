"""AI 分析的数据解释、模型调用及后台任务回归；不调用外部模型。"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from test_plugin import install_stubs, request_stub  # noqa: E402

install_stubs()
from core.analysis import BattleAnalysisService  # noqa: E402
from core.analysis_data import (  # noqa: E402
    ANALYSIS_DATA_PROMPT,
    DEFAULT_ANALYSIS_PROMPT,
    PREVIOUS_DEFAULT_ANALYSIS_PROMPT,
    build_analysis_data,
)
from core.models_detail import parse_battle_detail  # noqa: E402
from core.models_replay import parse_battle_replay  # noqa: E402
from core.service import GokService  # noqa: E402
from core.sqlite import AsyncSQLiteDB  # noqa: E402
from core.storage import GokStorage  # noqa: E402
from core.webui import WebUIService  # noqa: E402
from fixtures_expansion import detail_payload, replay_payload  # noqa: E402

ANSWER = "【2026-10-04 16:20】-【排位赛】-【妲己】\n【【获胜方】】\n【原因】：测试胜方协同推进。\n【关键点】：1:00 的推塔改变了地图空间。\n【【失败方】】\n【原因】：测试败方未及时回防。\n【关键点】：关键交战后人员脱节。\n【背锅】：证据不足，无法确定。"


def models():
    """使用已验证的解析器生成同场合成数据。

    Returns:
        单局详情与地图回顾，不包含账号凭据。
    """
    detail = parse_battle_detail(detail_payload(), "111")
    detail["profile"] = {"camp_id": "123456789", "role_id": "111"}
    detail["match"] = {
        "game_seq": "100001",
        "game_svr": "test-server",
        "relay_svr": "test-relay",
        "played_at": "2026-10-04 16:20",
        "mode_name": "排位赛",
        "hero_name": "妲己",
        "side": 1,
        "result": "win",
        "duration_sec": 180,
    }
    replay = parse_battle_replay(
        replay_payload(), "100", 180, detail["blue"] + detail["red"]
    )
    replay["match"] = detail["match"]
    return detail, replay


class AnalysisData(unittest.TestCase):
    def test_both_teams_all_players_events_and_damage_units_are_preserved(self):
        detail, replay = models()
        data = build_analysis_data(detail, replay)
        self.assertEqual(len(data["players"]), 10)
        self.assertEqual(len(data["trajectories"]), 10)
        self.assertEqual(len(data["events"]), len(replay["events"]))
        self.assertEqual(
            data["players"][0]["hero_damage"], detail["blue"][0]["hero_damage"]
        )
        self.assertEqual(
            data["players"][0]["total_damage"], detail["blue"][0]["total_damage"]
        )
        self.assertEqual(
            data["players"][0]["damage_taken"], detail["blue"][0]["damage_taken"]
        )
        self.assertEqual(data["winning_camp"], 1)

    def test_losing_query_player_does_not_become_winner(self):
        detail, replay = models()
        detail["head"] = {"acntCamp": 1, "gameResult": 0}
        detail["match"]["result"] = "lose"
        self.assertEqual(build_analysis_data(detail, replay)["winning_camp"], 2)

    def test_conflicting_outcomes_are_rejected(self):
        detail, replay = models()
        detail["head"] = {"acntCamp": 1, "gameResult": 0}
        with self.assertRaisesRegex(ValueError, "胜负信息不一致"):
            build_analysis_data(detail, replay)

    def test_unknown_winner_is_rejected_instead_of_guessed(self):
        detail, replay = models()
        detail["head"] = {}
        detail["match"]["result"] = "unknown"
        with self.assertRaisesRegex(ValueError, "胜负阵营"):
            build_analysis_data(detail, replay)

    def test_named_camp_from_real_match_model_is_understood(self):
        detail, replay = models()
        detail["head"] = {}
        detail["match"].update(side="blue", result="lose")
        data = build_analysis_data(detail, replay)
        self.assertEqual(data["winning_camp"], 2)
        self.assertEqual(data["queried_player"]["camp"], 1)

    def test_queried_hero_is_the_target_player_not_the_first_teammate(self):
        detail, replay = models()
        target = detail["red"][2]
        detail["target"] = target
        detail["match"].update(side="red", result="lose", hero_name=target["hero_name"])
        data = build_analysis_data(detail, replay)
        self.assertEqual(data["queried_player"]["player_id"], target["player_id"])
        self.assertEqual(data["queried_player"]["hero_name"], target["hero_name"])
        self.assertNotEqual(
            data["queried_player"]["hero_name"], detail["blue"][0]["hero_name"]
        )

    def test_missing_teams_or_replay_is_not_silently_replaced_by_stats_only(self):
        detail, replay = models()
        with self.assertRaisesRegex(ValueError, "双方"):
            build_analysis_data({**detail, "red": []}, replay)
        with self.assertRaisesRegex(ValueError, "地图回顾"):
            build_analysis_data(detail, {"available": False})

    def test_another_game_is_rejected(self):
        detail, replay = models()
        with self.assertRaisesRegex(ValueError, "不一致"):
            build_analysis_data(detail, {**replay, "match": {"game_seq": "other"}})

    def test_images_and_unrelated_credentials_are_excluded(self):
        detail, replay = models()
        detail["token"] = "private-token"
        detail["blue"][0]["userKey"] = "private-key"
        text = json.dumps(build_analysis_data(detail, replay))
        for value in ("private-token", "private-key", "heroIcon", "https://"):
            self.assertNotIn(value, text)

    def test_sampling_preserves_event_times_gap_edges_and_death_revive_points(self):
        detail, replay = models()
        points = [{"time_seconds": t, "position": {"x": t, "y": 50}} for t in range(21)]
        points[11]["position"] = None
        replay["players"][0].update(
            points=points,
            deaths=[{"time_seconds": 7, "position": None}],
            revives=[{"time_seconds": 18, "position": {"x": 1, "y": 99}}],
        )
        replay["events"] = [{"time_seconds": 3.5, "type": "kill"}]
        trajectory = build_analysis_data(detail, replay)["trajectories"][0]
        sent = {point[0]: point for point in trajectory["points"]}
        self.assertTrue({0, 3, 4, 5, 7, 10, 11, 12, 15, 18, 20}.issubset(sent))
        self.assertEqual(sent[11], [11, None, None])
        self.assertEqual(trajectory["raw_point_count"], 21)
        self.assertLess(trajectory["sent_point_count"], 21)

    def test_missing_damage_stays_null_and_true_zero_survives(self):
        detail, replay = models()
        detail["blue"][0].update(hero_damage=None, building_damage=0)
        row = build_analysis_data(detail, replay)["players"][0]
        self.assertIsNone(row["hero_damage"])
        self.assertEqual(row["building_damage"], 0)

    def test_config_default_matches_code_and_has_no_editable_system_prompt(self):
        config = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            config["analysis"]["items"]["prompt"]["default"], DEFAULT_ANALYSIS_PROMPT
        )
        self.assertEqual(
            set(config["analysis"]["items"]),
            {"prompt", "select_provider", "cache_retention_days"},
        )
        self.assertEqual(config["analysis"]["items"]["cache_retention_days"]["default"], 150)
        self.assertNotIn("comment", config)


class AnalysisCalls(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.detail, self.replay = models()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = AsyncSQLiteDB(Path(self.temp_dir.name) / "gok.db")
        await self.db.connect()
        self.storage = GokStorage(self.db)
        await self.storage.initialize()
        self.service = SimpleNamespace(
            ok=GokService.ok,
            err=GokService.err,
            storage=self.storage,
            battle_detail=AsyncMock(
                return_value=GokService.ok(self.detail, "detail.html")
            ),
            battle_replay=AsyncMock(return_value=GokService.ok(self.replay)),
        )
        self.context = SimpleNamespace(
            llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text=ANSWER))
        )
        self.config = {"analysis": {"select_provider": "chosen-model"}}
        self.analysis = BattleAnalysisService(self.service, self.context, self.config)

    async def asyncTearDown(self):
        await self.analysis.close()
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_native_call_separates_fixed_system_and_configurable_task(self):
        result = await self.analysis.analyze("123456789", 2, game_seq="100001")
        self.assertEqual(result["data"], ANSWER)
        self.assertFalse(result["temp"])
        call = self.context.llm_generate.await_args.kwargs
        self.assertEqual(call["chat_provider_id"], "chosen-model")
        self.assertEqual(call["system_prompt"], ANALYSIS_DATA_PROMPT)
        self.assertIn(DEFAULT_ANALYSIS_PROMPT, call["prompt"])
        self.service.battle_detail.assert_awaited_once_with(
            "123456789", 2, game_seq="100001"
        )
        self.assertIs(
            self.service.battle_replay.await_args.kwargs["detail_data"], self.detail
        )
        self.assertEqual(
            self.service.battle_replay.await_args.kwargs["game_seq"], "100001"
        )

    async def test_custom_task_and_json_braces_are_preserved(self):
        self.config["analysis"]["prompt"] = '只输出 JSON：{"结论":"内容"}'
        self.context.llm_generate.return_value.completion_text = '{"结论":"测试结果"}'
        result = await self.analysis.analyze("123456789")
        self.assertEqual(result["data"], '{"结论":"测试结果"}')
        self.assertIn(
            self.config["analysis"]["prompt"],
            self.context.llm_generate.await_args.kwargs["prompt"],
        )
        self.assertEqual(
            self.context.llm_generate.await_args.kwargs["system_prompt"],
            ANALYSIS_DATA_PROMPT,
        )

    async def test_missing_model_only_resolves_command_battle_and_does_not_call_model(self):
        self.config["analysis"]["select_provider"] = ""
        result = await self.analysis.analyze("123456789")
        self.assertIn("选择分析模型", result["msg"])
        self.service.battle_detail.assert_awaited_once()
        self.service.battle_replay.assert_not_awaited()
        self.context.llm_generate.assert_not_awaited()
        self.assertEqual((await self.analysis.start("123456789"))["code"], 400)

    async def test_detail_or_replay_errors_prevent_model_call(self):
        self.service.battle_detail.return_value = GokService.err("对局不存在")
        self.assertEqual(
            (await self.analysis.analyze("123456789"))["msg"], "对局不存在"
        )
        self.service.battle_replay.assert_not_awaited()
        self.service.battle_detail.return_value = GokService.ok(self.detail)
        self.service.battle_replay.return_value = GokService.err("回顾暂不可用")
        self.assertEqual(
            (await self.analysis.analyze("123456789"))["msg"], "回顾暂不可用"
        )
        self.context.llm_generate.assert_not_awaited()

    async def test_unavailable_replay_prevents_fake_comprehensive_analysis(self):
        self.service.battle_replay.return_value = GokService.ok({"available": False})
        self.assertEqual((await self.analysis.analyze("123456789"))["code"], 400)
        self.context.llm_generate.assert_not_awaited()

    async def test_default_format_accepts_fence_and_collapses_multiline_items(self):
        self.context.llm_generate.return_value.completion_text = (
            "```text\n" + ANSWER.replace("协同推进。", "协同\n推进。") + "\n```"
        )
        result = await self.analysis.analyze("123456789")
        self.assertEqual(len(result["data"].splitlines()), 8)
        self.assertNotIn("```", result["data"])

    async def test_header_uses_real_data_even_when_model_returns_placeholders(self):
        self.context.llm_generate.return_value.completion_text = ANSWER.replace(
            "【2026-10-04 16:20】-【排位赛】-【妲己】",
            "【对局时间】-【对局模式】-【所用英雄】",
        )
        result = await self.analysis.analyze("123456789")
        self.assertEqual(result["data"], ANSWER)
        self.assertNotIn("所用英雄", result["data"])
        await self.analysis.clear_cache("100001")
        self.context.llm_generate.return_value.completion_text = ANSWER.split("\n", 1)[
            1
        ]
        self.assertEqual((await self.analysis.analyze("123456789"))["data"], ANSWER)

    async def test_saved_previous_default_uses_new_prompt_and_real_header(self):
        self.config["analysis"]["prompt"] = PREVIOUS_DEFAULT_ANALYSIS_PROMPT
        result = await self.analysis.analyze("123456789")
        self.assertEqual(result["data"], ANSWER)
        self.assertIn(
            DEFAULT_ANALYSIS_PROMPT,
            self.context.llm_generate.await_args.kwargs["prompt"],
        )

    async def test_empty_or_invalid_format_returns_clear_error(self):
        for text in ("", "模型没有遵守要求"):
            self.context.llm_generate.return_value.completion_text = text
            self.assertEqual((await self.analysis.analyze("123456789"))["code"], 400)

    async def test_model_errors_do_not_expose_exception_secrets(self):
        self.context.llm_generate.side_effect = ValueError("private-key")
        result = await self.analysis.analyze("123456789")
        self.assertIn("ValueError", result["msg"])
        self.assertNotIn("private-key", result["msg"])

    async def test_timeout_cancels_model_and_releases_task(self):
        self.context.llm_generate.side_effect = lambda **kwargs: asyncio.sleep(10)

        # AsyncMock 返回协程不会自动等待嵌套协程，用真实异步副作用验证取消。
        async def blocked(**kwargs):
            await asyncio.sleep(10)

        self.context.llm_generate.side_effect = blocked
        with patch("core.analysis.ANALYSIS_TIMEOUT_SECONDS", 0.01):
            result = await self.analysis.analyze("123456789")
        self.assertIn("超时", result["msg"])
        self.assertFalse(self.analysis._tasks)

    async def test_jobs_progress_done_expiration_and_status_are_bounded(self):
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def delayed(**kwargs):
            entered.set()
            await gate.wait()
            return SimpleNamespace(completion_text=ANSWER)

        self.context.llm_generate.side_effect = delayed
        started = await self.analysis.start("123456789", 2, game_seq="100001")
        task_id = started["data"]["task_id"]
        self.assertEqual(self.analysis.status(task_id)["data"]["status"], "pending")
        await asyncio.wait_for(entered.wait(), 1)
        state = self.analysis.status(task_id)["data"]
        self.assertEqual(state["status"], "running")
        self.assertIn("分析", state["message"])
        gate.set()
        await asyncio.gather(*tuple(self.analysis._tasks))
        self.assertEqual(self.analysis.status(task_id)["data"]["text"], ANSWER)
        self.analysis._jobs[task_id]["expires_at"] = time.monotonic() - 1
        self.assertEqual(self.analysis.status(task_id)["code"], 400)
        self.assertEqual(self.analysis.status("missing")["code"], 400)

    async def test_job_failures_return_error_status(self):
        self.service.battle_detail.return_value = GokService.err("对局不存在")
        task_id = (await self.analysis.start("123456789"))["data"]["task_id"]
        await asyncio.gather(*tuple(self.analysis._tasks))
        self.assertEqual(self.analysis.status(task_id)["data"]["status"], "error")

    async def test_concurrency_limit_and_unload_cancel_all_tasks(self):
        gate = asyncio.Event()

        async def delayed(**kwargs):
            await gate.wait()

        self.context.llm_generate.side_effect = delayed
        for _ in range(3):
            self.assertEqual((await self.analysis.start("123456789"))["code"], 200)
        self.assertEqual((await self.analysis.start("123456789"))["code"], 400)
        tasks = tuple(self.analysis._tasks)
        await asyncio.sleep(0)
        await self.analysis.close()
        self.assertTrue(all(task.cancelled() for task in tasks))
        self.assertFalse(self.analysis._jobs)

    async def test_web_routes_require_selection_and_only_expose_status_text(self):
        web = WebUIService(self.service, self.analysis)
        request_stub.set_json({"keyword": "123456789"})
        self.assertEqual((await web.analysis_start()).status_code, 400)
        request_stub.set_json(
            {
                "keyword": "123456789",
                "game_seq": "100001",
                "index": 2,
                "system_prompt": "不应接受",
            }
        )
        response = await web.analysis_start()
        task_id = json.loads(response.body)["data"]["task_id"]
        await asyncio.gather(*tuple(self.analysis._tasks))
        request_stub.query = type(request_stub.query)({"task_id": task_id})
        state = json.loads((await web.analysis_status()).body)["data"]
        self.assertEqual(set(state), {"status", "message", "text"})
        self.assertEqual(state["text"], ANSWER)
        self.assertEqual(
            self.context.llm_generate.await_args.kwargs["system_prompt"],
            ANALYSIS_DATA_PROMPT,
        )

    async def test_saved_detail_replay_uses_same_game_without_second_detail_query(self):
        service = GokService(
            {},
            None,
            None,
            SimpleNamespace(get_battle_replay=AsyncMock(return_value=replay_payload())),
            None,
        )
        service.battle_detail = AsyncMock(
            side_effect=AssertionError("不应重复查询详情")
        )
        result = await service.battle_replay(
            "123456789", game_seq="100001", detail_data=self.detail
        )
        self.assertEqual(result["code"], 200)
        service.battle_detail.assert_not_awaited()
        self.assertEqual(
            (
                await service.battle_replay(
                    "123456789", game_seq="another", detail_data=self.detail
                )
            )["code"],
            400,
        )

    async def test_command_result_is_saved_and_web_reuses_it_without_upstream(self):
        self.assertEqual((await self.analysis.analyze("123456789", 2))["data"], ANSWER)
        saved = await self.analysis.cached("100001")
        self.assertEqual(saved["text"], ANSWER)
        self.config["analysis"]["select_provider"] = ""
        self.service.battle_detail.reset_mock()
        result = await self.analysis.start("other-player", game_seq="100001")
        self.assertEqual(result["data"], {"status": "done", "text": ANSWER})
        self.assertEqual((await self.analysis.analyze("other-player", game_seq="100001"))["data"], ANSWER)
        self.service.battle_detail.assert_not_awaited()
        self.context.llm_generate.assert_awaited_once()
        self.assertEqual((await self.analysis.cached("100001"))["created_at"], saved["created_at"])

    async def test_web_result_is_reused_by_command_and_uses_match_id_not_player_or_index(self):
        started = await self.analysis.start("123456789", 2, game_seq="100001")
        await asyncio.gather(*tuple(self.analysis._tasks))
        self.assertEqual(self.analysis.status(started["data"]["task_id"])["data"]["text"], ANSWER)
        self.config["analysis"]["select_provider"] = ""
        self.assertEqual((await self.analysis.analyze("another-player", 1))["data"], ANSWER)
        self.context.llm_generate.assert_awaited_once()
        self.service.battle_replay.assert_awaited_once()
        self.detail["match"]["game_seq"] = "100002"
        result = await self.analysis.analyze("another-player", 1)
        self.assertIn("选择分析模型", result["msg"])
        self.assertIsNone(await self.analysis.cached("100002"))

    async def test_persistent_results_survive_database_reopen_and_service_restart(self):
        await self.analysis.analyze("123456789")
        await self.analysis.close()
        await self.db.close()
        await self.db.connect()
        self.service.storage = GokStorage(self.db)
        await self.service.storage.initialize()
        self.analysis = BattleAnalysisService(self.service, self.context, self.config)
        await self.analysis.initialize()
        self.service.battle_detail.reset_mock()
        self.config["analysis"]["select_provider"] = ""
        self.assertEqual((await self.analysis.analyze("123456789", game_seq="100001"))["data"], ANSWER)
        self.service.battle_detail.assert_not_awaited()
        self.context.llm_generate.assert_awaited_once()

    async def test_expired_results_are_deleted_and_regenerated_with_current_retention(self):
        await self.storage.save_analysis("100001", "expired")
        await self.storage.save_analysis("other", "also expired")
        await self.db.execute("UPDATE battle_analyses SET created_at=?", (time.time() - 151 * 86400,))
        self.assertEqual((await self.analysis.analyze("123456789", game_seq="100001"))["data"], ANSWER)
        self.assertIsNone(await self.analysis.cached("other"))
        self.context.llm_generate.assert_awaited_once()
        await self.db.execute("UPDATE battle_analyses SET created_at=?", (time.time() - 8 * 86400,))
        self.assertIsNotNone(await self.analysis.cached("100001"))
        self.config["analysis"]["cache_retention_days"] = 7
        self.assertIsNone(await self.analysis.cached("100001"))
        self.assertEqual(await self.db.fetch_value("SELECT COUNT(*) FROM battle_analyses"), 0)

    async def test_retention_boundary_and_invalid_settings(self):
        self.config["analysis"]["cache_retention_days"] = 365
        self.assertEqual(self.analysis.retention_days, 365)
        for value in (None, "bad", 0, -1, float("inf")):
            self.config["analysis"]["cache_retention_days"] = value
            self.assertEqual(self.analysis.retention_days, 150)
        await self.db.execute("INSERT INTO battle_analyses VALUES (?,?,?)", ("boundary", ANSWER, 0))
        with patch("core.storage.time.time", return_value=150 * 86400):
            self.assertIsNone(await self.analysis.cached("boundary"))

    async def test_startup_and_idle_cleanup_remove_expired_rows(self):
        await self.storage.save_analysis("startup", ANSWER)
        await self.db.execute("UPDATE battle_analyses SET created_at=0")
        with patch("core.analysis.CACHE_CLEANUP_INTERVAL_SECONDS", 0.01):
            await self.analysis.initialize()
            self.assertEqual(await self.db.fetch_value("SELECT COUNT(*) FROM battle_analyses"), 0)
            await self.db.execute("INSERT INTO battle_analyses VALUES (?,?,?)", ("idle", ANSWER, 0))
            for _ in range(30):
                if await self.db.fetch_value("SELECT COUNT(*) FROM battle_analyses") == 0:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(await self.db.fetch_value("SELECT COUNT(*) FROM battle_analyses"), 0)
        cleanup = self.analysis._cleanup_task
        await self.analysis.close()
        self.assertTrue(cleanup.cancelled())

    async def test_concurrent_command_and_web_call_generate_one_result(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(**kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(completion_text=ANSWER)

        self.context.llm_generate.side_effect = delayed
        command = asyncio.create_task(self.analysis.analyze("123456789"))
        await asyncio.wait_for(entered.wait(), 1)
        started = await self.analysis.start("another-player", game_seq="100001")
        release.set()
        self.assertEqual((await command)["data"], ANSWER)
        await asyncio.gather(*tuple(self.analysis._tasks))
        self.assertEqual(self.analysis.status(started["data"]["task_id"])["data"]["text"], ANSWER)
        self.context.llm_generate.assert_awaited_once()
        self.service.battle_replay.assert_awaited_once()
        self.assertFalse(self.analysis._match_locks)

    async def test_clear_removes_only_selected_result_and_stale_job_then_allows_regeneration(self):
        started = await self.analysis.start("123456789", game_seq="100001")
        await asyncio.gather(*tuple(self.analysis._tasks))
        await self.storage.save_analysis("other", "other analysis")
        self.assertTrue(await self.analysis.clear_cache("100001"))
        self.assertFalse(await self.analysis.clear_cache("100001"))
        self.assertIsNone(await self.analysis.cached("100001"))
        self.assertEqual((await self.analysis.cached("other"))["text"], "other analysis")
        self.assertEqual(self.analysis.status(started["data"]["task_id"])["code"], 400)
        self.assertEqual((await self.analysis.analyze("123456789"))["data"], ANSWER)
        self.assertEqual(self.context.llm_generate.await_count, 2)

    async def test_clear_waits_for_running_generation_and_does_not_allow_cache_to_reappear(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(**kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(completion_text=ANSWER)

        self.context.llm_generate.side_effect = delayed
        command = asyncio.create_task(self.analysis.analyze("123456789"))
        await asyncio.wait_for(entered.wait(), 1)
        clear = asyncio.create_task(self.analysis.clear_cache("100001"))
        await asyncio.sleep(0)
        self.assertFalse(clear.done())
        release.set()
        await command
        self.assertTrue(await clear)
        self.assertIsNone(await self.analysis.cached("100001"))
        self.assertFalse(self.analysis._match_locks)

    async def test_cancelled_waiter_releases_match_lock_references(self):
        async with self.analysis._match_lock("100001"):
            waiter = asyncio.create_task(self.analysis.clear_cache("100001"))
            await asyncio.sleep(0)
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            self.assertEqual(self.analysis._match_locks["100001"][1], 1)
        self.assertFalse(self.analysis._match_locks)

    async def test_failed_or_mismatched_analysis_is_not_persisted(self):
        self.context.llm_generate.return_value.completion_text = "bad format"
        self.assertEqual((await self.analysis.analyze("123456789"))["code"], 400)
        self.assertIsNone(await self.analysis.cached("100001"))
        self.context.llm_generate.reset_mock()
        result = await self.analysis.analyze("123456789", game_seq="other")
        self.assertIn("标识", result["msg"])
        self.context.llm_generate.assert_not_awaited()
        self.assertIsNone(await self.analysis.cached("other"))

    async def test_database_write_failure_does_not_report_saved_success(self):
        with patch.object(self.storage, "save_analysis", AsyncMock(side_effect=OSError("private-path"))):
            result = await self.analysis.analyze("123456789")
        self.assertEqual(result["code"], 400)
        self.assertNotIn("private-path", result["msg"])
        self.assertIsNone(await self.analysis.cached("100001"))

    async def test_web_cache_and_clear_routes_validate_ids_and_never_call_model(self):
        web = WebUIService(self.service, self.analysis)
        request_stub.query = type(request_stub.query)({})
        self.assertEqual((await web.analysis_cache()).status_code, 400)
        request_stub.set_json({})
        self.assertEqual((await web.analysis_clear()).status_code, 400)
        request_stub.query = type(request_stub.query)({"game_seq": "100001"})
        data = json.loads((await web.analysis_cache()).body)["data"]
        self.assertEqual(data, {"available": False, "text": "", "created_at": None})
        await self.storage.save_analysis("100001", "<script>literal</script>")
        data = json.loads((await web.analysis_cache()).body)["data"]
        self.assertTrue(data["available"])
        self.assertEqual(data["text"], "<script>literal</script>")
        request_stub.set_json({"game_seq": "100001"})
        self.assertTrue(json.loads((await web.analysis_clear()).body)["data"]["deleted"])
        self.context.llm_generate.assert_not_awaited()
        self.service.battle_detail.assert_not_awaited()
        unavailable = WebUIService(self.service)
        self.assertEqual((await unavailable.analysis_cache()).status_code, 503)
        self.assertEqual((await unavailable.analysis_clear()).status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
