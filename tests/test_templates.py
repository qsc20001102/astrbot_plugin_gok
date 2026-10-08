"""模板自测：用样例数据真实渲染每个 HTML 模板，捕获语法/变量错误。

模板出错时消息层会降级为纯文本，用户只会看到「图片渲染失败」，
所以在离线阶段就把模板跑到通。渲染使用与插件相同的 autoescape 包裹方式。

运行：python tests/test_templates.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.template import TemplateRepository, secure_render_template  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label} {detail}".strip())
        print(f"  FAIL  {label} {detail}")


MATCH = {
    "external_id": "1",
    "played_at": "2026-10-06 12:00",
    "mode": "ranked",
    "mode_name": "排位赛",
    "hero_id": "107",
    "hero_name": "赵云",
    "hero_icon": "https://x/h.png",
    "result": "win",
    "result_text": "胜利",
    "win": True,
    "kills": 8,
    "deaths": 2,
    "assists": 10,
    "kda": 9.0,
    "score": 12.3,
    "score_text": "12.3",
    "duration_sec": 935,
    "duration_text": "15:35",
    "rank_name": "至尊星耀V",
    "stars": 5,
    "peak_score": 1500,
    "peak_delta": 20,
    "mvp": True,
    "mvp_type": "mvp",
    "mvp_icon": "https://x/mvp.png",
    "gold": True,
    "medal": "金牌打野",
    "medal_icon": "https://x/m.png",
    "evaluate": "MVP",
    "honor_text": "MVP · 金牌打野",
    "side": "blue",
}

PROFILE = {
    "camp_id": "123456789",
    "nickname": "测试玩家",
    "avatar": "https://x/a.png",
    "area": "wechat",
    "area_name": "微信区",
    "role_id": "111",
    "server_name": "微信389区",
    "current_rank": "最强王者",
    "current_stars": 12,
    "rank_label": "最强王者",
    "season_games": 120,
    "season_wins": 66,
    "win_rate": 55.0,
    "rank_score": 88,
    "peak_rating": 92,
    "peak_score": 1523,
    "mvp_count": 30,
    "gold_count": 9,
    "hide_match": False,
}

CASES: dict[str, dict] = {
    "helps.html": {},
    "battle.html": {
        "profile": PROFILE,
        "list": [
            MATCH,
            {
                **MATCH,
                "win": False,
                "result": "lose",
                "result_text": "失败",
                "mvp_type": "svp",
                "medal": "",
                "peak_delta": -15,
                "score": 0.0,
                "score_text": "-",
                "stars": 0,
                "rank_name": "",
                "hero_icon": "",
                "peak_score": None,
            },
        ],
        "summary": {
            "total": 25,
            "wins": 15,
            "loses": 10,
            "win_rate": 60.0,
            "avg_kda": 4.2,
            "avg_score": 10.5,
            "mvp_count": 6,
            "svp_count": 3,
            "gold_count": 8,
        },
    },
    "profile.html": {
        "profile": PROFILE,
        "season_heroes": [
            {
                "hero_id": "312",
                "hero_name": "沈梦溪",
                "hero_icon": "https://x/s.jpg",
                "games": 8,
                "wins": 8,
                "win_rate": 100.0,
                "fight_power": 6200,
            },
            {
                "hero_id": "151",
                "hero_name": "孙权",
                "hero_icon": "",
                "games": 3,
                "wins": 1,
                "win_rate": 33.3,
                "fight_power": None,
            },
        ],
        "season_name": "S42",
        "hide_match": False,
    },
    "profile_empty.html": {
        "profile": {
            **PROFILE,
            "avatar": "",
            "season_games": 0,
            "season_wins": 0,
            "win_rate": 0.0,
            "current_stars": 0,
            "peak_score": 0,
            "rank_score": 0,
            "peak_rating": 0,
            "gold_count": 0,
            "mvp_count": 0,
            "nickname": "新玩家",
            "hide_match": True,
        },
        "season_heroes": [],
        "season_name": "",
        "hide_match": True,
    },
    "detail.html": {
        "match": MATCH,
        "profile": PROFILE,
        "has_detail": True,
        "blue": [
            {
                "index": 1,
                "role_id": "111",
                "nickname": "玩家A",
                "hero_id": "107",
                "hero_name": "赵云",
                "hero_icon": "https://x/h.png",
                "level": 15,
                "kills": 8,
                "deaths": 2,
                "assists": 10,
                "money": 12000,
                "hurt": 90000,
                "behurt": 40000,
                "fight_power": 6800,
                "is_target": True,
            },
            {
                "index": 2,
                "role_id": "222",
                "nickname": "",
                "hero_id": "",
                "hero_name": "",
                "hero_icon": "",
                "level": 0,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "money": 0,
                "hurt": 0,
                "behurt": 0,
                "fight_power": 0,
                "is_target": False,
            },
        ],
        "red": [
            {
                "index": 1,
                "role_id": "333",
                "nickname": "玩家B",
                "hero_id": "106",
                "hero_name": "小乔",
                "hero_icon": "",
                "level": 14,
                "kills": 3,
                "deaths": 6,
                "assists": 4,
                "money": 9000,
                "hurt": 60000,
                "behurt": 30000,
                "fight_power": 0,
                "is_target": False,
            },
        ],
    },
    "detail_empty.html": {
        "match": MATCH,
        "profile": PROFILE,
        "has_detail": False,
        "blue": [],
        "red": [],
    },
    "aliases.html": {
        "list": [{"gokid": 123456789, "role_name": "小明", "alias": "朋友"}],
        "keyword": "",
    },
    "aliases_search.html": {
        "list": [],
        "keyword": "<script>alert(1)</script>",
    },
}


async def main() -> int:
    from jinja2.sandbox import SandboxedEnvironment

    repo = TemplateRepository(ROOT / "templates")
    env = SandboxedEnvironment(autoescape=True)

    print("[模板文件]")
    available = repo.available()
    check("模板目录非空", bool(available), str(available))
    for name in CASES:
        base = name.replace("_empty", "").replace("_search", "")
        if base.endswith(".html"):
            check(f"模板存在：{base}", base in available)

    print("\n[渲染]")
    rendered: dict[str, str] = {}
    for name, data in CASES.items():
        base = name.replace("_empty", "").replace("_search", "")
        try:
            source = await repo.get(base)
            template = env.from_string(secure_render_template(source))
            html = template.render(data=data, data_time="2026-10-06 12:00:00")
        except Exception as exc:  # noqa: BLE001
            check(f"渲染 {name}", False, f"{type(exc).__name__}: {exc}")
            continue
        rendered[name] = html
        ok = "<html" in html.lower() and "{{" not in html and "{%" not in html
        check(f"渲染 {name}（长度 {len(html)}）", ok)

    print("\n[转义安全]")
    search_html = rendered.get("aliases_search.html", "")
    check("恶意关键字被转义", "&lt;script&gt;" in search_html)
    check("未注入原始 script", "<script>alert(1)</script>" not in search_html)

    print("\n[内容抽查]")
    battle_html = rendered.get("battle.html", "")
    import re

    honors = re.findall(r'<div class="honor">(.*?)</div>', battle_html, re.S)
    check(
        "荣誉列只展示图片且无重复文本",
        bool(honors)
        and all(not re.sub(r"<[^>]*>", "", cell).strip() for cell in honors),
    )
    for name in ("battle.html", "profile.html", "detail.html"):
        html = rendered[name]
        check(
            f"{name} 模板铺满画布而非固定宽度",
            "width: 100%;" in html and "min-width:" in html,
        )
    for token in ("测试玩家", "赵云", "金牌打野", "胜利", "失败", "SVP", "15:35"):
        check(f"战绩页包含「{token}」", token in battle_html)

    profile_html = rendered.get("profile.html", "")
    for token in ("沈梦溪", "100%", "6,200", "微信389区", "最强王者"):
        check(f"资料页包含「{token}」", token in profile_html)
    # 隐藏战绩的玩家应出现提示
    check("隐藏战绩提示", "隐藏战绩" in rendered.get("profile_empty.html", ""))
    # 不应出现 None 字面量
    check("空资料页无 None 字样", "None" not in rendered.get("profile_empty.html", ""))

    detail_html = rendered.get("detail.html", "")
    check("详情页含双方", "蓝方" in detail_html and "红方" in detail_html)
    check("详情页标出目标玩家", "target" in detail_html)
    check(
        "详情图片不包含本场表现或地图回顾",
        "本场表现" not in detail_html and "地图回顾" not in detail_html,
    )
    check(
        "装备与召唤师技能分列",
        "<th>出装</th>" in detail_html and "<th>召唤师技能</th>" in detail_html,
    )
    check(
        "公共片段已合并，远端不依赖模板 include",
        "GOK:REPORT" not in detail_html and "share-track" in detail_html,
    )
    role_html = rendered.get("aliases.html", "")
    columns = re.findall(r"<th>(.*?)</th>", role_html)
    check(
        "角色图片只有昵称、营地ID、别名三列", columns == ["游戏昵称", "营地 ID", "别名"]
    )
    check(
        "角色营地ID没有千分位",
        "123456789" in role_html and "123,456,789" not in role_html,
    )

    print("\n" + "=" * 60)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
