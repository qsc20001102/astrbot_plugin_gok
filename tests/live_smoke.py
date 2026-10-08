"""端到端联调脚本：真实走一遍「扫码登录 → 查询指定营地 ID」。

需要你本人用微信扫码确认，因此只在你主动运行时使用：

    python tests/live_smoke.py                 # 登录后查询自己
    python tests/live_smoke.py 489048724       # 登录后查询指定营地 ID
    python tests/live_smoke.py 489048724 --auth <camp_auth.json>   # 复用已有登录态

它会：
1. 向营地申请登录二维码，保存为 JPEG 并打印路径；
2. 轮询扫码状态（默认 300 秒）；
3. 登录成功后，用拿到的登录态查询目标玩家的资料、赛季与最近战绩；
4. 打印规范化后的结果，用于验证加密协议与字段解析是否真的对得上。

登录态只写在临时目录，不会写入插件的正式数据目录。
"""

from __future__ import annotations

import asyncio
import base64
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from test_plugin import install_stubs  # noqa: E402

# 只模拟宿主接口，营地请求仍通过真实 HTTP 客户端发送。
install_stubs()

from core.camp_api import CampDataApi  # noqa: E402
from core.camp_auth import CampAuthStore  # noqa: E402
from core.camp_client import CampApiError, CampClient  # noqa: E402
from core.camp_login import CampLoginManager  # noqa: E402
from core.http import HttpClient  # noqa: E402
from core.models import (  # noqa: E402
    parse_battle_row,
    parse_profile,
    parse_season_stats,
)

POLL_TIMEOUT_SECONDS = 300
# 写到临时目录，避免把二维码留在插件仓库里。
# 注意：微信返回的是 JPEG，扩展名必须与真实格式一致。
QR_FILE = Path(tempfile.gettempdir()) / "gok_login_qr.jpg"


def parse_args(argv: list[str]) -> tuple[str, Path | None]:
    target = ""
    auth: Path | None = None
    rest = list(argv)
    if "--auth" in rest:
        idx = rest.index("--auth")
        if idx + 1 < len(rest):
            auth = Path(rest[idx + 1])
            del rest[idx : idx + 2]
    for item in rest:
        if item.isdigit():
            target = item
            break
    return target, auth


async def ensure_login(
    login: CampLoginManager, auth_store: CampAuthStore, reuse: Path | None
) -> tuple[str, str] | None:
    """返回 (账号ID, 昵称)；失败返回 None。"""
    if reuse and reuse.exists():
        store = CampAuthStore(reuse)
        accounts = await store.list_accounts()
        if accounts:
            print(f"[1/3] 复用登录态：{accounts[0].display_name}")
            await auth_store.upsert(accounts[0])
            return accounts[0].user_id, accounts[0].display_name

    print("[1/3] 正在申请登录二维码…")
    session, error = await login.create_session()
    if session is None:
        print(f"  失败：{error}")
        return None

    QR_FILE.write_bytes(base64.b64decode(session.qrcode_base64))
    print(f"  二维码已保存（JPEG）：{QR_FILE}")
    print(f"  有效期约 {session.remaining_seconds} 秒")
    print("  请用【微信】扫码并在手机上确认。\n")

    print("[2/3] 等待扫码…")
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last_status = ""
    while time.time() < deadline:
        result = await login.poll(session.task_id)
        status = result.get("status")
        if status != last_status:
            print(f"  状态：{status} {result.get('message', '')}")
            last_status = status
        if status == "success":
            account = result["account"]
            print(f"  登录成功：{account.display_name}（ID {account.user_id}）")
            print(f"  userKey 是否解出：{bool(account.resolve_user_key())}\n")
            return account.user_id, account.display_name
        if status in {"expired", "canceled"} or result.get("terminal"):
            print(f"  结束：{result.get('message', status)}")
            return None
        await asyncio.sleep(2)

    print("  超时未完成扫码。")
    return None


async def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    target, reuse = parse_args(sys.argv[1:])

    http = HttpClient(timeout=20, verify_ssl=True)
    auth_path = Path(tempfile.mkdtemp(prefix="gok_live_")) / "camp_auth.json"
    auth_store = CampAuthStore(auth_path)
    login = CampLoginManager(http, auth_store=auth_store)
    client = CampClient(http, auth_store)
    api = CampDataApi(client)

    try:
        logged = await ensure_login(login, auth_store, reuse)
        if logged is None:
            return 1
        camp_id = target or logged[0]
        print(f"[3/3] 查询营地 ID：{camp_id}\n")

        print("=" * 72)
        print("[资料]")
        try:
            payload = await api.get_profile(camp_id)
        except CampApiError as exc:
            print(f"  失败：code={exc.code} message={exc}")
            return 1
        profile = parse_profile(payload, camp_id)
        print(f"  昵称：{profile.nickname}")
        print(
            f"  区服：{profile.server_name or profile.area_name}（{profile.area_name}）"
        )
        print(
            f"  角色ID：{profile.role_id}  段位：{profile.rank_label} {profile.current_stars}星"
        )
        print(
            f"  隐藏战绩(hideMatch)：{profile.hide_match}  头像：{'有' if profile.avatar else '无'}"
        )

        if profile.role_id:
            try:
                season = parse_season_stats(await api.get_season_page(profile.role_id))
                if season:
                    print(
                        f"  赛季 {season.season_name}：{season.season_games} 场 / "
                        f"胜 {season.season_wins} / 金牌 {season.gold_count} / "
                        f"巅峰 {season.peak_score}"
                    )
                    for hero in season.heroes[:5]:
                        print(
                            f"    · {hero['hero_name']} {hero['games']} 场 "
                            f"胜 {hero['wins']} 胜率 {hero['win_rate']}%"
                        )
                else:
                    print("  赛季页：无有效数据")
            except CampApiError as exc:
                print(f"  赛季页失败：code={exc.code} message={exc}")

        print("=" * 72)
        print("[战绩]")
        try:
            battles = await api.fetch_battles(camp_id, max_pages=2, max_matches=10)
        except CampApiError as exc:
            print(f"  失败：code={exc.code} message={exc}")
            return 1

        rows = battles["list"]
        print(
            f"  拉取 {len(rows)} 场（{battles['pages']} 页，has_more={battles['has_more']}）"
        )
        if not rows:
            if profile.hide_match:
                print("  该玩家隐藏了战绩（hideMatch=1），属正常业务限制。")
            else:
                print("  没有对局数据。")
            return 0

        for index, row in enumerate(rows[:10]):
            m = parse_battle_row(row, index)
            print(
                f"    {m.played_at_text}  {m.hero_name:<6} {m.mode_name:<8} "
                f"{m.result_text} {m.kills}/{m.deaths}/{m.assists} "
                f"评分 {m.score_text:<5} {m.honor_text:<14} {m.duration_text}  "
                f"{m.rank_name} {m.stars}星 巅峰 {m.peak_score}/{m.peak_delta}"
            )

        print("\n端到端联调通过。")
        return 0
    finally:
        await http.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
