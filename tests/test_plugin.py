"""插件层集成自测：在不启动 AstrBot 的前提下验证装配、指令分发与页面路由。

做法是用 `sys.modules` 注入一份与宿主 API 等价的**桩模块**（签名依据本仓库
AstrBot 源码核对：`Context.register_web_api`、`filter.event_message_type`、
`StarTools.get_data_dir`、`Star.html_render`、`astrbot.api.web` 等），
然后把插件当作包导入并真实跑一遍指令。

运行：python tests/test_plugin.py
不发网络请求：所有用例都走「无登录态」或纯本地别名路径。
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
PARENT = ROOT.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(ROOT))

PASSED: list[str] = []
FAILED: list[str] = []

_DATA_DIR: Path = Path(tempfile.gettempdir()) / "gok_stub_data"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label} {detail}".strip())
        print(f"  FAIL  {label} {detail}")


# --------------------------------------------------------------------- 桩：日志
class _Logger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _log(self, level: str, message: object, *args: object) -> None:
        text = str(message)
        if args:
            try:
                text = text % args
            except (TypeError, ValueError):
                text = f"{text} {args}"
        self.records.append((level, text))

    def debug(self, message: object, *args: object) -> None:
        self._log("debug", message, *args)

    def info(self, message: object, *args: object) -> None:
        self._log("info", message, *args)

    def warning(self, message: object, *args: object) -> None:
        self._log("warning", message, *args)

    def error(self, message: object, *args: object) -> None:
        self._log("error", message, *args)

    def exception(self, message: object, *args: object) -> None:
        self._log("exception", message, *args)

    def messages(self) -> str:
        return "\n".join(text for _, text in self.records)


logger_stub = _Logger()


# --------------------------------------------------------------------- 桩：消息
class MessageChain:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def message(self, text: str) -> MessageChain:
        self.parts.append(f"text:{text}")
        return self

    def file_image(self, path: str) -> MessageChain:
        self.parts.append(f"image:{path}")
        return self


class _Result:
    def __init__(self, kind: str, payload: object) -> None:
        self.kind = kind
        self.payload = payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Result {self.kind}={self.payload!r}>"


class AstrMessageEvent:
    """最小可用的事件桩，字段与宿主一致。"""

    def __init__(self, message_str: str = "") -> None:
        self.message_str = message_str
        self.message_obj = types.SimpleNamespace(message_str=message_str)
        self.unified_msg_origin = "test:session"
        self.sent: list[_Result] = []
        self.stopped = False
        self.llm_blocked: bool | None = None

    def stop_event(self) -> None:
        self.stopped = True

    def should_call_llm(self, call_llm: bool) -> None:
        self.llm_blocked = call_llm

    def plain_result(self, text: str) -> _Result:
        return _Result("plain", text)

    def image_result(self, url: str) -> _Result:
        return _Result("image", url)

    def chain_result(self, chain: MessageChain) -> _Result:
        return _Result("chain", chain)

    async def send(self, result: _Result) -> None:
        self.sent.append(result)

    def texts(self) -> str:
        return "\n".join(
            str(r.payload) for r in self.sent if r.kind in {"plain", "image"}
        )


class _EventMessageType:
    ALL = "ALL"
    GROUP_MESSAGE = "GROUP_MESSAGE"
    PRIVATE_MESSAGE = "PRIVATE_MESSAGE"


class _Filter:
    EventMessageType = _EventMessageType
    decorated: list[str] = []

    @staticmethod
    def event_message_type(event_type: object, priority: int = 0):
        def decorator(func):
            _Filter.decorated.append(getattr(func, "__name__", "?"))
            func.__event_type__ = event_type
            func.__priority__ = priority
            return func

        return decorator

    @staticmethod
    def command(*args: object, **kwargs: object):
        def decorator(func):
            return func

        return decorator


# --------------------------------------------------------------------- 桩：Star
class _StarTools:
    @staticmethod
    def get_data_dir(plugin_name: str | None = None) -> Path:
        path = _DATA_DIR / (plugin_name or "unknown")
        path.mkdir(parents=True, exist_ok=True)
        return path


class _Star:
    def __init__(self, context: object, config: object | None = None) -> None:
        self.context = context
        self.rendered: list[tuple[str, dict]] = []

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        return_url: bool = True,
        options: dict | None = None,
    ) -> str:
        from jinja2 import Environment

        rendered_html = Environment(autoescape=True).from_string(tmpl).render(**data)
        if "<html" not in rendered_html.lower():
            raise AssertionError(
                "Star.html_render requires HTML source, not a filename"
            )
        self.rendered.append((tmpl, data))
        if return_url:
            return "http://stub.invalid/render.png"
        return str(_DATA_DIR / "render.png")

    async def text_to_image(self, text: str, return_url: bool = True) -> str:
        return "http://stub.invalid/text.png"


class _Context:
    def __init__(self) -> None:
        self.routes: list[tuple[str, object, list[str], str]] = []

    def register_web_api(
        self, route: str, handler: object, methods: list[str], desc: str
    ) -> None:
        self.routes.append((route, handler, methods, desc))

    async def get_current_chat_provider_id(self, umo: str = "") -> str:
        return "stub-provider"

    async def llm_generate(self, chat_provider_id: str = "", prompt: str = ""):
        return types.SimpleNamespace(completion_text="这是一句锐评")


def _register(*args: object, **kwargs: object):
    def decorator(cls):
        cls.__register_args__ = args
        return cls

    return decorator


# --------------------------------------------------------------------- 桩：web
def json_response(data=None, *, status_code: int = 200, headers=None):
    # Match the host: json_response sends the given body without an envelope.
    return JSONResponse(
        {} if data is None else data, status_code=status_code, headers=headers
    )


def error_response(message: str, *, status_code: int = 400, data=None, headers=None):
    return json_response(
        {"status": "error", "message": message, "data": data},
        status_code=status_code,
        headers=headers,
    )


class _Query(dict):
    def get(self, key, default=None, type=None):  # noqa: A002 - 模拟宿主签名
        value = super().get(key, default)
        if type is not None and value is not None:
            try:
                return type(value)
            except (TypeError, ValueError):
                return default
        return value


class _Request:
    def __init__(self) -> None:
        self.query = _Query()
        self.username = "stub-user"
        self._json: dict = {}

    def set_json(self, payload: dict) -> None:
        self._json = payload

    async def json(self, default=None):
        return self._json if self._json is not None else default


request_stub = _Request()


# --------------------------------------------------------------------- 安装桩
def install_stubs() -> None:
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")
    web = types.ModuleType("astrbot.api.web")

    class AstrBotConfig(dict):
        pass

    api.AstrBotConfig = AstrBotConfig
    api.logger = logger_stub
    api.html_renderer = None

    event.AstrMessageEvent = AstrMessageEvent
    event.MessageChain = MessageChain
    event.filter = _Filter
    event.MessageEventResult = _Result

    star.Context = _Context
    star.Star = _Star
    star.StarTools = _StarTools
    star.register = _register

    web.json_response = json_response
    web.error_response = error_response
    web.request = request_stub

    astrbot.api = api
    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.star": star,
            "astrbot.api.web": web,
        }
    )


# --------------------------------------------------------------------- 用例
async def run_tests() -> None:
    install_stubs()

    import importlib

    module = importlib.import_module("astrbot_plugin_gok.main")
    check("插件模块可导入", module is not None)
    check(
        "注册装饰器参数完整",
        len(getattr(module.GokPlugin, "__register_args__", ())) == 5,
    )
    check("消息入口已注册装饰器", "on_all_message" in _Filter.decorated)

    context = _Context()
    config = {
        "prefix": {"enable": False, "text": "王者"},
        "battle_limit": 10,
        "account_cooldown": 300,
        "tls_verify": True,
        "comment": {"enable": True, "select_provider": ""},
        "image": {"format": "jpeg", "device_scale_factor": "1.3", "jpeg_quality": 100},
    }
    plugin = module.GokPlugin(context, config)
    await plugin.initialize()
    try:
        await exercise(plugin, context, module, config)
    finally:
        # 必须关闭：aiosqlite 的后台线程不关闭会让解释器挂住不退出
        await plugin.terminate()
    check("terminate 释放了连接", plugin.db is None and plugin.http is None)


async def exercise(plugin, context, module, config) -> None:
    print("\n[装配]")
    check("指令表已填充", len(plugin.command_map) == 13, str(len(plugin.command_map)))
    check("页面路由已注册", len(context.routes) == 12, str(len(context.routes)))
    route_paths = {r[0] for r in context.routes}
    for expected in (
        "dashboard",
        "login/status",
        "login/qrcode",
        "login/poll",
        "login/cancel",
        "accounts/delete",
        "accounts/clear",
        "accounts/check",
        "query",
        "aliases/list",
        "aliases/update",
        "aliases/delete",
    ):
        check(
            f"路由存在：{expected}",
            f"/{module.PLUGIN_NAME}/{expected}" in route_paths,
        )
    check(
        "路由带插件名前缀",
        all(r[0].startswith(f"/{module.PLUGIN_NAME}/") for r in context.routes),
    )
    check("数据库文件已创建", plugin.db_path.exists(), str(plugin.db_path))
    check("未登录时给出提示", "尚未登录" in logger_stub.messages())
    check("服务层不再持有缓存参数", not hasattr(plugin.service, "cache_ttl"))
    check("插件不再读取缓存配置", not hasattr(plugin, "cache_ttl"))

    print("\n[消息解析 / 前缀]")
    check(
        "无前缀拆分正常",
        plugin.parse_message("战绩 123456789") == ["战绩", "123456789"],
    )
    check("空消息返回 None", plugin.parse_message("   ") is None)
    plugin.prefix_enabled = True
    plugin.prefix_text = "王者"
    check("前缀匹配后剥离", plugin.parse_message("王者战绩 123") == ["战绩", "123"])
    check("不匹配前缀则忽略", plugin.parse_message("战绩 123") is None)
    plugin.prefix_enabled = False

    print("\n[指令分发：别名（纯本地）]")
    event = AstrMessageEvent("角色添加 123456789 小明")
    results = [r async for r in plugin.on_all_message(event)]
    check("聊天不再提供手动添加角色", not event.stopped and not event.sent)
    check("无额外 yield", results == [], str(results))
    await plugin.storage.remember_player(123456789, "小明")
    event2 = AstrMessageEvent("角色修改 123456789 重复")
    await anext_result(plugin.on_all_message(event2))
    check("聊天不再提供手动修改角色", not event2.stopped and not event2.sent)

    event3 = AstrMessageEvent("角色查看")
    before = len(plugin.rendered)
    await anext_result(plugin.on_all_message(event3))
    check(
        "角色查看固定文本输出",
        len(plugin.rendered) == before and all(r.kind == "plain" for r in event3.sent),
    )
    check(
        "角色文本包含名字和ID",
        "小明" in event3.texts() and "123456789" in event3.texts(),
    )

    event4 = AstrMessageEvent("角色查询 小明")
    await anext_result(plugin.on_all_message(event4))
    check("角色查询指令已移除", not event4.stopped and not event4.sent)

    event5 = AstrMessageEvent("角色删除 123456789")
    await anext_result(plugin.on_all_message(event5))
    check("名称映射仅在管理页维护", not event5.stopped and not event5.sent)
    await plugin.storage.delete_alias(123456789)

    print("\n[指令分发：错误与降级]")
    event6 = AstrMessageEvent("战绩")
    await anext_result(plugin.on_all_message(event6))
    check("缺少参数时给出用法提示", "请提供营地 ID" in event6.texts(), event6.texts())

    # 没有登录态时，查询应给出「未登录」提示而不是抛异常
    event7 = AstrMessageEvent("战绩 123456789")
    await anext_result(plugin.on_all_message(event7))
    check("未登录时提示扫码", "营地" in event7.texts(), event7.texts())

    event8 = AstrMessageEvent("资料 123")
    await anext_result(plugin.on_all_message(event8))
    check("非法营地 ID 被拒绝", "5~15" in event8.texts(), event8.texts())

    event9 = AstrMessageEvent("资料 不存在的别名")
    await anext_result(plugin.on_all_message(event9))
    check("未知别名给出提示", "未找到" in event9.texts(), event9.texts())

    event10 = AstrMessageEvent("这是一句普通聊天")
    results10 = [r async for r in plugin.on_all_message(event10)]
    check("普通消息不响应", results10 == [] and not event10.sent)

    event11 = AstrMessageEvent("功能")
    await anext_result(plugin.on_all_message(event11))
    check(
        "功能说明固定文本",
        "战绩" in event11.texts() and all(r.kind == "plain" for r in event11.sent),
    )

    print("\n[输出模式与原生 HTML 渲染]")
    config["query_output"] = "文本"
    plugin._setup_config()
    check("配置页面文本选项生效", plugin.query_output == "text")
    config["query_output"] = "图片"
    plugin._setup_config()
    check("配置页面图片选项生效", plugin.query_output == "image")
    import importlib.util

    fixture_spec = importlib.util.spec_from_file_location(
        "gok_output_fixtures", ROOT / "tests/test_templates.py"
    )
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture_module)
    for command, method, template in (
        ("战绩", "battle_report", "battle.html"),
        ("资料", "player_overview", "profile.html"),
        ("对局", "battle_detail", "detail.html"),
    ):
        result = plugin.service.ok(fixture_module.CASES[template], temp=template)
        with patch.object(
            plugin.service, method, AsyncMock(return_value=result)
        ) as action:
            plugin.query_output = "text"
            text_event = AstrMessageEvent(f"{command} 489048724")
            before = len(plugin.rendered)
            await anext_result(plugin.on_all_message(text_event))
            check(
                f"{command} 文本模式不调用渲染",
                len(plugin.rendered) == before
                and all(r.kind == "plain" for r in text_event.sent),
            )
            check(
                f"{command} 文本包含关键角色信息",
                "测试玩家" in text_event.texts()
                and "查询完成" not in text_event.texts(),
            )
            plugin.query_output = "image"
            image_event = AstrMessageEvent(f"{command} 489048724")
            await anext_result(plugin.on_all_message(image_event))
            check(
                f"{command} 图片模式传入完整HTML并发送图片",
                any(r.kind == "image" for r in image_event.sent)
                and "<html" in plugin.rendered[-1][0].lower()
                and plugin.rendered[-1][1]["data"] == result["data"],
            )
            if command == "战绩":
                arg_event = AstrMessageEvent("战绩 489048724 3")
                await anext_result(plugin.on_all_message(arg_event))
                check(
                    "带场数指令将参数转换为整数", action.await_args.kwargs["limit"] == 3
                )

    check(
        "独立锐评指令已移除",
        "锐评" not in plugin.command_map and "战绩锐评" not in plugin.command_map,
    )
    custom_prompt = '请温柔点评，输出 JSON：{"点评":"内容"}'
    plugin.comment_prompt = custom_prompt
    for mode in ("text", "image"):
        plugin.query_output = mode
        review_event = AstrMessageEvent("战绩 489048724")
        observed = []

        async def review_after_send(**kwargs):
            observed.append(
                {
                    "prompt": kwargs["prompt"],
                    "first_kind": review_event.sent[0].kind
                    if review_event.sent
                    else None,
                }
            )
            return types.SimpleNamespace(completion_text="测试自动锐评")

        with (
            patch.object(
                plugin.service,
                "battle_report",
                AsyncMock(
                    return_value=plugin.service.ok(
                        fixture_module.CASES["battle.html"], temp="battle.html"
                    )
                ),
            ),
            patch.object(
                context, "llm_generate", AsyncMock(side_effect=review_after_send)
            ),
        ):
            await anext_result(plugin.on_all_message(review_event))
        check(
            f"{mode} 战绩发送后自动跟发一次锐评",
            len(observed) == 1
            and len(review_event.sent) == 2
            and review_event.sent[-1].payload == "测试自动锐评"
            and observed[0]["first_kind"] == ("plain" if mode == "text" else "image"),
        )
        check(
            "自定义提示词保留JSON括号并附带实际对局",
            observed[0]["prompt"].startswith(custom_prompt)
            and '"killcnt": 8' in observed[0]["prompt"],
        )

    plugin.query_output = "text"
    for enabled, result in (
        (
            False,
            plugin.service.ok(fixture_module.CASES["battle.html"], temp="battle.html"),
        ),
        (True, plugin.service.err("查询失败")),
    ):
        plugin.comment_enabled = enabled
        failed_or_disabled = AstrMessageEvent("战绩 489048724")
        with (
            patch.object(
                plugin.service, "battle_report", AsyncMock(return_value=result)
            ),
            patch.object(context, "llm_generate", AsyncMock()) as model,
        ):
            await anext_result(plugin.on_all_message(failed_or_disabled))
            check(
                "关闭锐评或查询失败不会调用模型",
                model.await_count == 0 and len(failed_or_disabled.sent) == 1,
            )
    plugin.comment_enabled = True
    send_failure = AstrMessageEvent("战绩 489048724")
    with (
        patch.object(
            plugin.service,
            "battle_report",
            AsyncMock(
                return_value=plugin.service.ok(
                    fixture_module.CASES["battle.html"], temp="battle.html"
                )
            ),
        ),
        patch.object(
            send_failure, "send", AsyncMock(side_effect=RuntimeError("send failure"))
        ),
        patch.object(context, "llm_generate", AsyncMock()) as model,
    ):
        try:
            await plugin.cmd_battle(send_failure, "489048724")
        except RuntimeError:
            check("数据发送失败不追加锐评", model.await_count == 0)
        else:
            check("数据发送失败不追加锐评", False)
    plugin.query_output = "image"
    battle_fallback = AstrMessageEvent("战绩 489048724")
    with (
        patch.object(
            plugin.service,
            "battle_report",
            AsyncMock(
                return_value=plugin.service.ok(
                    fixture_module.CASES["battle.html"], temp="battle.html"
                )
            ),
        ),
        patch.object(
            plugin,
            "html_render",
            AsyncMock(side_effect=RuntimeError("renderer unavailable")),
        ),
        patch.object(
            context,
            "llm_generate",
            AsyncMock(
                return_value=types.SimpleNamespace(completion_text="回退文本后的锐评")
            ),
        ),
    ):
        await plugin.cmd_battle(battle_fallback, "489048724")
        check(
            "图片失败但文本发送成功仍追加锐评",
            len(battle_fallback.sent) == 2
            and "文本结果" in battle_fallback.sent[0].payload
            and battle_fallback.sent[1].payload == "回退文本后的锐评",
        )
    with (
        patch.object(
            plugin.service,
            "player_overview",
            AsyncMock(
                return_value=plugin.service.ok(
                    fixture_module.CASES["profile.html"], temp="profile.html"
                )
            ),
        ),
        patch.object(
            plugin,
            "html_render",
            AsyncMock(side_effect=RuntimeError("renderer unavailable")),
        ),
    ):
        fallback_event = AstrMessageEvent("资料 489048724")
        await anext_result(plugin.on_all_message(fallback_event))
        check(
            "渲染失败回退到真实资料文本",
            "测试玩家" in fallback_event.texts()
            and "文本结果" in fallback_event.texts(),
        )

    print("\n[页面接口]")

    def handler_for(name: str):
        suffix = f"/{module.PLUGIN_NAME}/{name}"
        for route, func, _methods, _desc in context.routes:
            if route == suffix:
                return func
        raise KeyError(name)

    dash_response = await handler_for("dashboard")()
    dash = json.loads(dash_response.body)
    check("dashboard 返回 HTTP 200", dash_response.status_code == 200)
    check("dashboard 含账号信息", "accounts" in dash)

    await plugin.storage.remember_player(555666777, "自动保存")
    request_stub.set_json({"gokid": 555666777, "name": "管理页修改"})
    added = await handler_for("aliases/update")()
    check(
        "管理页可修改显示名称",
        added.status_code == 200 and json.loads(added.body).get("updated"),
    )
    listed = json.loads((await handler_for("aliases/list")()).body)
    check(
        "页面可列出别名",
        any(row.get("name") == "管理页修改" for row in listed.get("list", [])),
    )

    request_stub.set_json({"gokid": 555666777})
    deleted = await handler_for("aliases/delete")()
    check(
        "页面可删除别名",
        deleted.status_code == 200 and json.loads(deleted.body).get("deleted"),
    )

    request_stub.query = _Query({"keyword": "", "type": "battle"})
    bad = json.loads((await handler_for("query")()).body)
    check("空关键字查询被拒", bad.get("status") == "error", str(bad))

    request_stub.query = _Query({"keyword": "123456789", "type": "battle"})
    no_login = json.loads((await handler_for("query")()).body)
    check("未登录查询返回可读错误", no_login.get("status") == "error", str(no_login))
    check(
        "没有开放手动添加名称的路由",
        not any(path.endswith("/aliases/add") for path in route_paths),
    )
    with patch.object(
        plugin.client,
        "validate_accounts",
        AsyncMock(
            return_value={
                "checked": 2,
                "valid": 1,
                "invalid": 1,
                "uncertain": 0,
                "results": [],
            }
        ),
    ):
        checked = json.loads((await handler_for("accounts/check")()).body)
        check(
            "登录态检测结果保留完整响应",
            checked["checked"] == 2
            and checked["valid"] == 1
            and checked["invalid"] == 1,
        )
    check(
        "错误信息可读",
        "营地" in str(no_login.get("message", "")),
        str(no_login.get("message")),
    )

    request_stub.set_json({"task_id": ""})
    polled = json.loads((await handler_for("login/poll")()).body)
    check("轮询缺少 task_id 时被拒", polled.get("status") == "error", str(polled))

    status_response = await handler_for("login/status")()
    status = json.loads(status_response.body)
    check("login/status 可用", status_response.status_code == 200)
    check("无会话时 active=False", status.get("active") is False)

    missing = json.loads((await handler_for("accounts/delete")()).body)
    check("删除账号缺少参数时被拒", missing.get("status") == "error", str(missing))

    request_stub.set_json({"user_id": "test"})
    with patch.object(
        plugin.auth_store, "remove", AsyncMock(side_effect=PermissionError("read-only"))
    ):
        failed_delete = await handler_for("accounts/delete")()
        check(
            "删除写入失败返回明确错误",
            failed_delete.status_code == 500
            and "写入权限" in json.loads(failed_delete.body)["message"],
        )
    with patch.object(
        plugin.auth_store, "clear", AsyncMock(side_effect=PermissionError("read-only"))
    ):
        failed_clear = await handler_for("accounts/clear")()
        check(
            "清空写入失败不会报告成功",
            failed_clear.status_code == 500
            and json.loads(failed_clear.body)["status"] == "error",
        )

    request_stub.set_json({"task_id": "terminal-test"})
    with patch.object(
        plugin.login,
        "poll",
        AsyncMock(
            return_value={"status": "error", "message": "换票失败", "terminal": True}
        ),
    ):
        failure = json.loads((await handler_for("login/poll")()).body)
        check(
            "登录终止错误传递给页面",
            failure["terminal"] and failure["message"] == "换票失败",
        )

    for kind, method, data in (
        (
            "battle",
            "battle_report",
            {"list": [{"hero_name": "鲁班大师", "kills": 2}], "summary": {"total": 1}},
        ),
        ("profile", "player_overview", {"profile": {"nickname": "飞翔小野猪丨"}}),
        (
            "detail",
            "battle_detail",
            {"blue": [{"nickname": "飞翔小野猪丨"}], "red": []},
        ),
    ):
        request_stub.query = _Query({"keyword": "489048724", "type": kind})
        with patch.object(
            plugin.service, method, AsyncMock(return_value=plugin.service.ok(data))
        ):
            response = await handler_for("query")()
        body = json.loads(response.body)
        # PluginPagePage.vue sends response.data?.data ?? response.data to the SDK.
        bridged = body.get("data") if body.get("data") is not None else body
        check(
            f"{kind} 查询经宿主解包后保留类型和玩家数据",
            response.status_code == 200
            and bridged["type"] == kind
            and bridged["data"] == data,
        )

    print("\n[前端约束]")
    # 插件页面运行在 sandbox iframe（无 allow-modals）中：
    # window.confirm/alert 会被静默忽略，必须用页面内弹窗。
    app_js = ROOT / "pages" / "camp-console" / "app.js"
    source = app_js.read_text(encoding="utf-8")
    for banned in ("window.confirm(", "window.alert(", "window.prompt("):
        check(f"未使用被 sandbox 禁用的 {banned.rstrip('(')}", banned not in source)
    check("使用页面内确认框", "askConfirm" in source)
    check("启动时恢复扫码会话", "resumeSession" in source)
    # 页面不得读写 web storage（不透明源会抛异常）；用属性访问形式判断，
    # 避免注释里提到这两个名字就误报
    check("未使用 localStorage", "localStorage." not in source)
    check("未使用 sessionStorage", "sessionStorage." not in source)
    # 不再有缓存相关 UI
    check("页面无已缓存玩家区块", "player-list" not in source)
    check("页面无缓存统计区块", "renderStats" not in source)


async def anext_result(agen) -> None:
    """驱动一次异步生成器（吞掉 StopAsyncIteration）。"""
    try:
        async for _ in agen:
            pass
    except StopAsyncIteration:
        pass


def main() -> int:
    global _DATA_DIR
    # ignore_cleanup_errors：SQLite 会留下 -wal/-shm，Windows 上清理可能失败
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        _DATA_DIR = Path(tmp)
        asyncio.run(run_tests())

    print("\n" + "=" * 60)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
