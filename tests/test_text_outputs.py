"""简明文本输出回归，不依赖 AstrBot、账号凭据或外部网络。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.text_formatters import format_service_text  # noqa: E402
from test_templates import CASES  # noqa: E402


class TextOutputs(unittest.TestCase):
    def result(self, template, data):
        return {"code": 200, "temp": template, "data": data}

    def test_profile_keeps_identity_rank_and_season(self):
        text = format_service_text(self.result("profile.html", CASES["profile.html"]))
        self.assertIn("资料｜测试玩家", text)
        self.assertIn("ID 123456789", text)
        self.assertIn("最强王者 12星", text)
        self.assertIn("120场 / 66胜", text)
        self.assertIn("沈梦溪 8场 100%", text)
        self.assertLessEqual(len(text.splitlines()), 6)

    def test_hidden_profile_and_missing_stats_are_clear(self):
        text = format_service_text(
            self.result("profile.html", CASES["profile_empty.html"])
        )
        self.assertIn("暂无统计", text)
        self.assertIn("战绩已隐藏", text)
        self.assertNotIn("None", text)
        self.assertNotIn("胜率 0%", text)

    def test_profile_text_includes_game_status(self):
        for label in ("离线", "在线", "游戏中", "未知"):
            data = {
                **CASES["profile.html"],
                "profile": {**CASES["profile.html"]["profile"], "game_status": label},
            }
            text = format_service_text(self.result("profile.html", data))
            self.assertIn(f"状态：{label}", text)
        text = format_service_text(self.result("profile.html", {"profile": {}}))
        self.assertIn("状态：未知", text)

    def test_battles_keep_order_mode_and_both_results(self):
        text = format_service_text(self.result("battle.html", CASES["battle.html"]))
        self.assertIn("全部战绩｜测试玩家", text)
        self.assertIn("近 25 场", text)
        self.assertIn("胜 · 赵云", text)
        self.assertIn("负 · 赵云", text)
        self.assertIn("MVP", text)
        self.assertIn("SVP", text)
        self.assertIn("展示 2 场", text)

    def test_unknown_result_is_not_reported_as_a_loss(self):
        data = {
            "profile": {},
            "list": [{"result": "unknown", "score": 0}],
            "summary": {},
        }
        text = format_service_text(self.result("battle.html", data))
        self.assertNotIn("负 ·", text)
        self.assertIn("— · 未知英雄", text)

    def test_detail_drops_long_equipment_lines_but_keeps_teams(self):
        data = {**CASES["detail.html"]}
        data["blue"] = [
            {**data["blue"][0], "score": 0, "equipment": [{"name": "不应展开的装备"}]}
        ]
        text = format_service_text(self.result("detail.html", data))
        self.assertIn("蓝方", text)
        self.assertIn("红方", text)
        self.assertIn("玩家A · 赵云 8/2/10 · 0分", text)
        self.assertNotIn("不应展开的装备", text)
        self.assertNotIn("本场表现", text)

    def test_role_list_preserves_id_and_only_three_fields(self):
        data = {
            "list": [
                {
                    "role_name": "小明",
                    "gokid": 123456789012345,
                    "alias": "",
                    "created_at": "不展示",
                }
            ]
        }
        text = format_service_text(self.result("aliases.html", data))
        self.assertIn("123456789012345", text)
        self.assertIn("小明 | 123456789012345 | —", text)
        self.assertNotIn("123,456", text)
        self.assertNotIn("不展示", text)

    def test_errors_and_existing_text_are_preserved(self):
        self.assertEqual(
            format_service_text({"code": 400, "msg": "登录态失效"}), "登录态失效"
        )
        self.assertEqual(format_service_text({"code": 200, "data": "已完成"}), "已完成")
        self.assertEqual(
            format_service_text({"code": 200, "data": {"text": "业务说明"}}), "业务说明"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
