"""Offline verification of search transport, name resolution, and selection."""

from __future__ import annotations

import asyncio
import base64
import importlib
import importlib.util
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from test_plugin import (  # noqa: E402
    AstrMessageEvent,
    _Context,
    _Query,
    anext_result,
    install_stubs,
    request_stub,
)

install_stubs()

# Exercise the host implementation when present, without starting AstrBot.
host_waiter = ROOT.parents[2] / "astrbot/core/utils/session_waiter.py"
if host_waiter.is_file():
    message = types.ModuleType("astrbot.core.message")
    components = types.ModuleType("astrbot.core.message.components")
    components.BaseMessageComponent = object
    platform = types.ModuleType("astrbot.core.platform")
    platform.AstrMessageEvent = AstrMessageEvent
    sys.modules.update(
        {
            "astrbot.core.message": message,
            "astrbot.core.message.components": components,
            "astrbot.core.platform": platform,
        }
    )
    spec = importlib.util.spec_from_file_location(
        "astrbot.core.utils.session_waiter", host_waiter
    )
    host_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = host_module
    spec.loader.exec_module(host_module)

from core import xxtea  # noqa: E402
from core.camp_api import CampDataApi  # noqa: E402
from core.camp_auth import CampAccount, CampAuthStore  # noqa: E402
from core.camp_client import CampApiError, CampClient  # noqa: E402
from core.camp_search import build_search_request, parse_search_response  # noqa: E402
from core.http import HttpClient, HttpResponse  # noqa: E402
from core.service import GokService  # noqa: E402
from core.sqlite import AsyncSQLiteDB  # noqa: E402
from core.storage import GokStorage  # noqa: E402
from test_core import SAMPLE_BATTLE, SAMPLE_PROFILE  # noqa: E402

# test_core installs API stubs; restore the chosen waiter for the plugin import.
if host_waiter.is_file():
    sys.modules["astrbot.core.utils.session_waiter"] = host_module

RESPONSE = bytes.fromhex(
    "1207737563636573731a95010a9201ca014412428801a18d061206e5908ce5908d"
    "1a1f68747470733a2f2f6578616d706c652e746573742f6176617461722e706e67"
    "500ae20106e6989fe88080aa0206515131e58cbaca014812468801a28d061206e5908ce5908d"
    "1a1f68747470733a2f2f6578616d706c652e746573742f6176617461722e706e67"
    "5014e20106e78e8be88085aa020ae5beaee4bfa132e58cba"
)
PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool) -> None:
    """Record one observable behavior.

    Args:
        label: Assertion description.
        condition: Whether the behavior passed.
    """
    (PASSED if condition else FAILED).append(label)
    print(f"{'PASS' if condition else 'FAIL'} {label}")


async def deliver(
    module, text: str, sender: str = "test-sender", origin: str = "test:session"
) -> bool:
    """Deliver a reply through the host waiter or the portable API stub.

    Args:
        module: Plugin module.
        text: Reply text.
        sender: Sender identity.
        origin: Conversation identity.

    Returns:
        Whether the reply matched a registered selection session.
    """
    waiter = sys.modules["astrbot.core.utils.session_waiter"]
    event = AstrMessageEvent(text)
    event.sender_id = sender
    event.unified_msg_origin = origin
    key = module.PlayerSelectionFilter().filter(event)
    entry = waiter.USER_SESSIONS.get(key)
    if entry is None:
        return False
    if isinstance(entry, tuple):
        controller, handler, _selector = entry
        await handler(controller, event)
    else:
        await waiter.SessionWaiter.trigger(key, event)
    return True


async def protocol_and_transport() -> None:
    """Verify byte preservation, parsing, and account retries.

    Returns:
        None. Records assertions.
    """
    check(
        "中文搜索请求符合已验证字节向量",
        build_search_request("祈无恙").hex()
        == "08f3071209e7a588e697a0e681991801200a3a0130",
    )
    users = parse_search_response(RESPONSE)["data"]["users"]
    check(
        "重复营地ID不会生成重复选择项",
        parse_search_response(RESPONSE + RESPONSE)["data"]["users"] == users,
    )
    check(
        "多用户与长消息长度正确解析",
        [user["uid"] for user in users] == ["100001", "100002"]
        and users[1]["region"] == "微信2区",
    )
    check(
        "没有候选是成功的空结果",
        parse_search_response(b"\x12\x07success")["data"]["users"] == [],
    )
    check(
        "错误状态不会伪装成搜索无结果",
        parse_search_response(b"\x12\x03bad")["returnCode"] != 0,
    )
    for raw in (b"\x12\x08success", b"\x80" * 12, b"\x00", b"\x13", b""):
        try:
            parse_search_response(raw)
        except ValueError:
            check("截断或非法响应被拒绝", True)
        else:
            check("截断或非法响应被拒绝", False)

    with tempfile.TemporaryDirectory() as tmp:
        store = CampAuthStore(Path(tmp) / "auth.json")
        first = CampAccount(user_id="100001", token="first-token", user_key="test-key")
        second = CampAccount(
            user_id="100002", token="second-token", user_key="test-key"
        )
        await store.upsert(first)
        await store.upsert(second)
        seen = []

        async def request(method, url, **kwargs):
            seen.append(kwargs)
            if len(seen) == 1:
                return HttpResponse(
                    200, headers={"returncode": "-30107", "returnmsg": "操作频繁"}
                )
            return HttpResponse(
                200, headers={"Content-Type": "application/x-protobuf"}, body=RESPONSE
            )

        http = Mock()
        http.request = AsyncMock(side_effect=request)
        client = CampClient(http, store)
        result = await CampDataApi(client).search_users("同名")
        check(
            "频控时搜索复用账号池换号",
            len(result) == 2
            and len(seen) == 2
            and seen[0]["headers"]["token"] != seen[1]["headers"]["token"],
        )
        check(
            "二进制请求不会经JSON编码",
            all(
                item["data"] == build_search_request("同名")
                and "json_body" not in item
                and item["headers"]["Content-Type"] == "application/x-protobuf"
                for item in seen
            ),
        )
        encrypted = base64.b64encode(xxtea.encrypt(RESPONSE, b"test-key")).decode()
        parsed = CampClient._parse_response(
            HttpResponse(200, headers={"campencrypt": "true"}, text=encrypted),
            first,
            protobuf=True,
        )
        check("搜索解密保留原始二进制", parsed["data"]["users"] == users)
        parsed = CampClient._parse_response(
            HttpResponse(200, text='{"returnCode":-1,"returnMsg":"登录态失效"}'),
            first,
            protobuf=True,
        )
        try:
            CampClient._raise_for_business_error(parsed)
        except CampApiError as error:
            check("搜索JSON鉴权错误沿用登录失效识别", error.code == "auth")
        try:
            CampClient._parse_response(
                HttpResponse(200, body=b"bad"), first, protobuf=True
            )
        except CampApiError as error:
            check("坏Protobuf不会错误冷却登录态", error.code == "upstream")
        check(
            "响应对象保留非UTF8字节",
            HttpResponse(200, body=b"\xff\x80").body == b"\xff\x80",
        )

    from aiohttp import web

    app = web.Application()

    async def binary_response(request):
        return web.Response(body=RESPONSE, content_type="application/x-protobuf")

    app.router.add_get("/search", binary_response)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    http = HttpClient()
    try:
        response = await http.request("GET", f"http://127.0.0.1:{port}/search")
        check("真实HTTP读取保留完整Protobuf字节", response.body == RESPONSE)
    finally:
        await http.close()
        await runner.cleanup()


async def resolution_and_migration() -> None:
    """Verify lookup order, successful persistence, modes, and migration.

    Returns:
        None. Records assertions.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = AsyncSQLiteDB(Path(tmp) / "names.db")
        await db.connect()
        try:
            await db.execute(
                "CREATE TABLE aliases (gokid INTEGER PRIMARY KEY,name TEXT NOT NULL,role_name TEXT NOT NULL,manually_named INTEGER NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL)"
            )
            await db.execute(
                "INSERT INTO aliases VALUES (100001,'旧手工别名','旧游戏昵称',1,1,2),(100002,'自动昵称','自动昵称',0,3,4)"
            )
            storage = GokStorage(db)
            await storage.initialize()
            await storage.initialize()
            rows = await storage.list_aliases()
            check(
                "旧库手工名称迁移为独立别名",
                next(row for row in rows if row["gokid"] == 100001)["alias"]
                == "旧手工别名",
            )
            check(
                "旧库自动昵称不伪造成别名",
                next(row for row in rows if row["gokid"] == 100002)["alias"] == "",
            )
            check(
                "数据库保留三项明确字段与创建时间",
                set(rows[0])
                == {"gokid", "role_name", "alias", "created_at", "updated_at"}
                and rows[1]["created_at"] == 1,
            )
            await storage.remember_player(100001, "同名")
            await storage.update_alias(100002, "同名")
            api = Mock()
            api.search_users = AsyncMock(
                return_value=parse_search_response(RESPONSE)["data"]["users"]
            )
            api.get_profile = AsyncMock(return_value=SAMPLE_PROFILE)
            api.get_season_page = AsyncMock(return_value={"data": {}})
            mixed = [
                SAMPLE_BATTLE,
                dict(SAMPLE_BATTLE, gameSeq="peak", mapName="巅峰赛"),
                dict(SAMPLE_BATTLE, gameSeq="fun", mapName="匹配赛"),
            ]
            api.fetch_battles = AsyncMock(return_value={"list": mixed})
            service = GokService({}, storage, Mock(), api, Mock())
            camp_id, error = await service.require_camp_id("100003")
            check(
                "数字营地ID直接解析",
                camp_id == 100003
                and error is None
                and api.search_users.await_count == 0,
            )
            camp_id, error = await service.require_camp_id("同名")
            check(
                "别名优先于另一个用户的游戏昵称",
                camp_id == 100002 and api.search_users.await_count == 0,
            )
            camp_id, _ = await service.require_camp_id("自动昵称")
            check(
                "别名不匹配时按真实昵称取ID",
                camp_id == 100002 and api.search_users.await_count == 0,
            )
            _, error = await service.require_camp_id("不存在于库")
            check(
                "本地未命中返回在线多候选且不查战绩",
                len(error["data"]["candidates"]) == 2
                and api.get_profile.await_count == api.fetch_battles.await_count == 0,
            )
            api.search_users.return_value = [{"uid": "100004", "name": "营地昵称"}]
            result = await service.battle_report("在线唯一昵称")
            row = next(
                row for row in await storage.list_aliases() if row["gokid"] == 100004
            )
            check(
                "唯一在线结果成功后保存真实游戏昵称",
                result["code"] == 200
                and row["role_name"] == "测试玩家"
                and row["alias"] == "",
            )
            searches = api.search_users.await_count
            await service.battle_report("测试玩家")
            check(
                "再次使用游戏昵称直接命中本地", api.search_users.await_count == searches
            )
            await storage.update_alias(100004, "人为别名")
            await storage.remember_player(100004, "改名后角色")
            row = next(
                row for row in await storage.list_aliases() if row["gokid"] == 100004
            )
            check(
                "自动刷新昵称不修改人工别名",
                row["role_name"] == "改名后角色" and row["alias"] == "人为别名",
            )
            await service.update_alias(100004, "")
            check(
                "别名可以清除且不改变昵称ID",
                (await service.require_camp_id("改名后角色"))[0] == 100004
                and next(
                    row
                    for row in await storage.list_aliases()
                    if row["gokid"] == 100004
                )["alias"]
                == "",
            )
            for option, mode in ((0, None), (1, "ranked"), (4, "peak")):
                result = await service.battle_report("100004", option=option)
                items = result["data"]["list"]
                check(
                    f"战绩类型{option}请求与结果一致",
                    api.fetch_battles.await_args.kwargs["option"] == option
                    and (
                        len(items) == 3
                        if mode is None
                        else len(items) == 1 and items[0]["mode"] == mode
                    ),
                )
            api.fetch_battles.side_effect = CampApiError("请求失败", "upstream")
            api.search_users.return_value = [{"uid": "100005", "name": "失败候选"}]
            result = await service.battle_report("失败查询")
            check(
                "失败的在线查询不写名称映射",
                result["code"] != 200 and not await storage.find_aliases("100005"),
            )

            client = Mock()
            client.request = AsyncMock(
                side_effect=[
                    {
                        "data": {
                            "list": [{"gameSeq": "1"}],
                            "hasMore": True,
                            "lastTime": "next",
                        }
                    },
                    {"data": {"list": [{"gameSeq": "2"}], "hasMore": False}},
                ]
            )
            await CampDataApi(client).fetch_battles("100004", option=4, page_delay=0)
            check(
                "巅峰筛选跨页保持并传递游标",
                all(
                    call.args[1]["option"] == 4
                    for call in client.request.await_args_list
                )
                and client.request.await_args_list[1].args[1]["lastTime"] == "next",
            )
        finally:
            await db.close()


async def selection_and_web() -> None:
    """Verify selections through the host API and immutable web fields.

    Returns:
        None. Records assertions.
    """
    module = importlib.import_module("astrbot_plugin_gok.main")
    import test_plugin

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        test_plugin._DATA_DIR = Path(tmp)
        plugin = module.GokPlugin(
            _Context(), {"query_output": "文本", "comment": {"enable": False}}
        )
        await plugin.initialize()
        waiter = sys.modules["astrbot.core.utils.session_waiter"]
        candidates = parse_search_response(RESPONSE)["data"]["users"]
        plugin.api.search_users = AsyncMock(return_value=candidates)
        action = AsyncMock(return_value=plugin.service.ok("战绩结果"))
        plugin.service.battle_report = action
        try:
            event = AstrMessageEvent("排位战绩 同名 5")
            task = asyncio.create_task(anext_result(plugin.on_all_message(event)))
            for _ in range(100):
                if event.sent:
                    break
                await asyncio.sleep(0.002)
            check(
                "同名候选以编号文本展示且含区服段位",
                "1. 同名" in event.texts()
                and "2. 同名" in event.texts()
                and "微信2区" in event.texts()
                and not action.called,
            )
            check(
                "其他发送人的选择不会触发",
                not await deliver(module, "1", sender="other-sender"),
            )
            check(
                "其他聊天的选择不会触发",
                not await deliver(module, "1", origin="other:session"),
            )
            await deliver(module, "9")
            check("非法序号保持选择并且不查询", not task.done() and not action.called)
            await deliver(module, "2")
            await asyncio.wait_for(task, 2)
            check(
                "选择继续原排位查询并保留场数",
                action.await_args.args == ("100002",)
                and action.await_args.kwargs == {"limit": 5, "option": 1},
            )
            check(
                "选择后清理所有等待状态",
                not waiter.USER_SESSIONS
                and not plugin._selection_tasks
                and not plugin._pending_choices,
            )
            for command, option in (("战绩", 0), ("巅峰战绩", 4)):
                event = AstrMessageEvent(f"{command} 100001 3")
                await anext_result(plugin.on_all_message(event))
                check(
                    f"{command}使用正确模式",
                    action.await_args.kwargs == {"limit": 3, "option": option},
                )

            calls = action.await_count
            event = AstrMessageEvent("战绩 同名")
            task = asyncio.create_task(anext_result(plugin.on_all_message(event)))
            for _ in range(100):
                if event.sent:
                    break
                await asyncio.sleep(0.002)
            await deliver(module, "取消")
            await asyncio.wait_for(task, 2)
            check(
                "取消选择不查询且释放会话",
                action.await_count == calls and not waiter.USER_SESSIONS,
            )
            with patch.object(module, "PLAYER_SELECTION_TIMEOUT", 0.03):
                event = AstrMessageEvent("战绩 同名")
                await anext_result(plugin.on_all_message(event))
            check(
                "超时结束不查数据并提示重发",
                "选择已超时" in event.texts()
                and action.await_count == calls
                and not waiter.USER_SESSIONS,
            )

            await plugin.storage.remember_player(100001, "固定昵称")
            request_stub.set_json({"gokid": 100001, "alias": "新别名"})
            response = await plugin.webui.aliases_update()
            check("管理页可以设置独立别名", response.status_code == 200)
            for field in ("name", "role_name", "camp_id"):
                request_stub.set_json(
                    {"gokid": 100001, "alias": "篡改", field: "不允许"}
                )
                response = await plugin.webui.aliases_update()
                check(f"管理页拒绝修改{field}", response.status_code == 400)
            row = next(
                row
                for row in await plugin.storage.list_aliases()
                if row["gokid"] == 100001
            )
            check(
                "拒绝修改后保留真实昵称营地ID和别名",
                row["role_name"] == "固定昵称" and row["alias"] == "新别名",
            )
            request_stub.set_json({"gokid": 100001, "alias": ""})
            check(
                "管理页支持清空别名",
                (await plugin.webui.aliases_update()).status_code == 200,
            )
            request_stub.query = _Query(
                {"keyword": "在线同名", "type": "battle", "option": "4"}
            )
            with patch.object(
                plugin.service,
                "battle_report",
                AsyncMock(
                    return_value={"code": 400, "data": {"candidates": candidates}}
                ),
            ):
                response = await plugin.webui.query_player()
            import json

            body = json.loads(response.body)["data"]
            check(
                "网页多候选保留查询模式",
                body["type"] == "selection"
                and body["option"] == 4
                and len(body["data"]["candidates"]) == 2,
            )

            event = AstrMessageEvent("战绩 在线同名")
            task = asyncio.create_task(anext_result(plugin.on_all_message(event)))
            for _ in range(100):
                if event.sent:
                    break
                await asyncio.sleep(0.002)
            await plugin.terminate()
            await asyncio.gather(task, return_exceptions=True)
            check(
                "插件卸载取消选择并清理宿主会话",
                not waiter.USER_SESSIONS and not plugin._selection_tasks,
            )
        finally:
            await plugin.terminate()


async def main() -> int:
    """Run the offline extension suite.

    Returns:
        Nonzero when any assertion fails.
    """
    await protocol_and_transport()
    await resolution_and_migration()
    await selection_and_web()
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    return int(bool(FAILED))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
