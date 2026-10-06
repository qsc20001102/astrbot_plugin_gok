"""王者营地数据查询插件入口。

数据来源是王者营地官方接口（`kohcamp.qq.com`）：先在插件页面用微信扫码登录，
再用登录态查询玩家数据，不再依赖任何第三方数据接口。

本文件只负责「装配 + 分发」：协议与业务逻辑在 `core/`，Web 接口在 `core/webui.py`，
渲染模板在 `templates/`，插件页面在 `pages/`。
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from pathlib import Path
from sys import maxsize
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .core.camp_api import CampDataApi
from .core.camp_auth import CampAuthStore
from .core.camp_client import CampClient
from .core.camp_login import CampLoginManager
from .core.heroes import hero_repository
from .core.http import HttpClient
from .core.message import DEFAULT_COMMENT_PROMPT, MessageSender
from .core.service import GokService
from .core.sqlite import AsyncSQLiteDB
from .core.storage import GokStorage
from .core.webui import WebUIService

PLUGIN_NAME = "astrbot_plugin_gok"


@register(
    PLUGIN_NAME,
    "飞翔大野猪",
    "通过王者营地官方接口实时查询王者荣耀玩家数据（扫码登录，无需第三方接口）",
    "2.4.1",
    "https://github.com/qsc20001102/astrbot_plugin_gok",
)
class GokPlugin(Star):
    """王者营地数据查询：战绩 / 资料 / 对局详情 / 战绩锐评，支持角色别名。

    首次使用需在 AstrBot 管理面板的插件页面用微信扫码登录王者营地。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.conf: Any = config or {}

        # 指令表先置空，保证 initialize 完成前的消息处理是安全的
        self.command_map: dict[str, Any] = {}

        self._setup_config()
        self._setup_paths()
        self._create_components()

        # 注册插件页面接口（页面本体由宿主自动发现 pages/ 目录）
        self.webui.register(context, PLUGIN_NAME)

        logger.info(
            "GOK 插件已初始化（前缀：%s · 实时查询不缓存 · 英雄目录 %d 条）",
            self.prefix_text if self.prefix_enabled else "未启用",
            hero_repository.count,
        )

    # ------------------------------------------------------------------ 配置
    def _setup_config(self) -> None:
        prefix = self.conf.get("prefix", {}) or {}
        self.prefix_enabled = bool(prefix.get("enable", False))
        self.prefix_text = str(prefix.get("text") or "").strip()
        if self.prefix_enabled and not self.prefix_text:
            logger.warning("指令前缀已开启但内容为空，将按未启用前缀处理")
            self.prefix_enabled = False

        comment = self.conf.get("comment", {}) or {}
        self.comment_enabled = bool(comment.get("enable", False))
        self.comment_provider = str(comment.get("select_provider") or "").strip()
        self.comment_prompt = str(
            comment.get("prompt") or DEFAULT_COMMENT_PROMPT
        ).strip()
        if self.comment_enabled:
            logger.info(
                "战绩锐评已启用（模型：%s）", self.comment_provider or "会话默认模型"
            )

        self.default_limit = self._int_config("battle_limit", 10, minimum=1, maximum=25)
        self._account_cooldown = self._int_config("account_cooldown", 300, minimum=0)
        self.request_timeout = float(self._int_config("request_timeout", 15, minimum=5))
        self.tls_verify = self.conf.get("tls_verify", True) is not False
        self.query_output = (
            "text"
            if self.conf.get("query_output", "图片") in ("文本", "text")
            else "image"
        )

    def _int_config(
        self, key: str, default: int, minimum: int = 0, maximum: int | None = None
    ) -> int:
        try:
            value = int(self.conf.get(key, default))
        except (TypeError, ValueError):
            return default
        value = max(minimum, value)
        return value if maximum is None else min(maximum, value)

    def _setup_paths(self) -> None:
        # 可写数据目录：data/plugin_data/astrbot_plugin_gok
        self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        self.plugin_dir = Path(__file__).resolve().parent
        self.db_path = self.data_dir / "gok.db"
        self.auth_path = self.data_dir / "camp_auth.json"
        logger.debug("插件数据目录：%s", self.data_dir)

    def _create_components(self) -> None:
        """手工装配依赖（构造函数注入）。"""
        self.db = AsyncSQLiteDB(self.db_path)
        self.storage = GokStorage(self.db)
        self.auth_store = CampAuthStore(self.auth_path, self._account_cooldown)
        self.http = HttpClient(timeout=self.request_timeout, verify_ssl=self.tls_verify)
        self.client = CampClient(self.http, self.auth_store)
        self.api = CampDataApi(self.client)
        self.login = CampLoginManager(self.http, auth_store=self.auth_store)
        self.sender = MessageSender(self.conf.get("image", {}) or {}, plugin=self)
        self.service = GokService(
            self.conf,
            self.storage,
            self.auth_store,
            self.api,
            self.login,
        )
        self.webui = WebUIService(self.service)

    # ------------------------------------------------------------------ 生命周期
    async def initialize(self) -> None:
        """实例化后由框架调用：连库、建表、补齐登录态字段。"""
        try:
            await self.db.connect()
            await self.storage.initialize()
            await self.auth_store.ensure_user_keys()
        except Exception:
            logger.exception("GOK 插件初始化失败")
            raise

        self._ini_command_map()

        summary = await self.auth_store.summary()
        if summary["logged_in"]:
            logger.info("营地登录态就绪：%s", summary["nickname"])
        else:
            logger.warning(
                "尚未登录王者营地，请在 AstrBot 管理面板 → 插件 → 王者营地查询 页面扫码登录"
            )
        logger.info("GOK 异步初始化完成")

    async def terminate(self) -> None:
        """插件卸载/停用时释放资源。"""
        if getattr(self, "http", None) is not None:
            await self.http.close()
            self.http = None
        if getattr(self, "db", None) is not None:
            await self.db.close()
            self.db = None
        logger.info("GOK 插件已卸载/停用")

    # ------------------------------------------------------------------ 指令表
    def _ini_command_map(self) -> None:
        self.command_map = {
            # 帮助
            "功能": self.cmd_helps,
            "帮助": self.cmd_helps,
            "王者功能": self.cmd_helps,
            "王者帮助": self.cmd_helps,
            # 查询
            "战绩": self.cmd_battle,
            "王者战绩": self.cmd_battle,
            "资料": self.cmd_profile,
            "王者资料": self.cmd_profile,
            "对局": self.cmd_detail,
            "对局详情": self.cmd_detail,
            # 角色别名
            "角色查看": self.cmd_alias_list,
            # 账号
            "营地登录": self.cmd_login,
            "营地账号": self.cmd_accounts,
        }

    # ------------------------------------------------------------------ 消息解析
    def parse_message(self, text: str) -> list[str] | None:
        """按前缀配置切分消息；启用前缀时不匹配的消息直接忽略。"""
        text = (text or "").strip()
        if not text:
            return None
        if self.prefix_enabled:
            prefix = self.prefix_text
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
            else:
                return None
        return text.split() or None

    def resolve_command(
        self, event: AstrMessageEvent
    ) -> tuple[str, list[str], Any] | None:
        """依次尝试处理后的文本与平台原始文本，兼容被其它插件改写的情况。"""
        seen: list[str] = []
        primary = getattr(event, "message_str", "") or ""
        if isinstance(primary, str) and primary.strip():
            seen.append(primary.strip())

        message_obj = getattr(event, "message_obj", None)
        raw = getattr(message_obj, "message_str", "") if message_obj else ""
        if isinstance(raw, str) and raw.strip() and raw.strip() not in seen:
            seen.append(raw.strip())

        for text in seen:
            parts = self.parse_message(text)
            if not parts:
                continue
            handler = self.command_map.get(parts[0])
            if handler:
                return parts[0], parts[1:], handler
        return None

    # ------------------------------------------------------------------ 参数注入
    @staticmethod
    async def _call_with_auto_args(
        handler: Any, event: AstrMessageEvent, args: list[str]
    ) -> Any:
        """按函数签名注入 event 与命令行参数，并按注解做类型转换。"""
        call_args: list[Any] = []
        arg_index = 0

        for param in inspect.signature(handler).parameters.values():
            if param.name == "self":
                continue
            if param.name == "event":
                call_args.append(event)
                continue
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                call_args.extend(args[arg_index:])
                arg_index = len(args)
                continue

            if arg_index < len(args):
                raw_value = args[arg_index]
                arg_index += 1
                try:
                    if param.annotation in (int, "int"):
                        call_args.append(int(raw_value))
                    elif param.annotation in (float, "float"):
                        call_args.append(float(raw_value))
                    else:
                        call_args.append(raw_value)
                except (TypeError, ValueError):
                    if param.default is inspect.Parameter.empty:
                        raise ValueError(
                            f"参数「{param.name}」格式不正确：{raw_value}"
                        ) from None
                    call_args.append(param.default)
            elif param.default is not inspect.Parameter.empty:
                call_args.append(param.default)
            else:
                raise ValueError(f"缺少参数「{param.name}」，请输入「功能」查看用法")

        return await handler(*call_args)

    # ------------------------------------------------------------------ 消息入口
    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize - 10)
    async def on_all_message(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[Any, None]:
        """最低优先级兜底：前面的插件与默认链路都不处理时才认领。"""
        if not self.command_map:
            return

        resolved = self.resolve_command(event)
        if not resolved:
            return

        command, args, handler = resolved
        # 认领消息，避免其它插件重复响应
        event.stop_event()
        # 注意宿主语义：这里的 True 表示「禁止默认 LLM 请求」（默认值是 False），
        # 避免本插件的查询结果又被默认模型回复一遍。
        event.should_call_llm(True)

        try:
            result = await self._call_with_auto_args(handler, event, args)
            if result is not None:
                yield result
        except ValueError as exc:
            await event.send(event.plain_result(str(exc)))
        except Exception as exc:  # noqa: BLE001 - 单条指令失败不应影响后续消息
            logger.exception("指令执行失败：%s（%s）", command, type(exc).__name__)
            await event.send(event.plain_result("处理失败，请稍后再试"))

    # ------------------------------------------------------------------ 指令实现
    async def cmd_helps(self, event: AstrMessageEvent) -> None:
        """功能说明。"""
        prefix = self.prefix_text if self.prefix_enabled else ""
        text = (
            "王者营地查询\n"
            f"{prefix}战绩 营地ID/角色名 [场数]：最近战绩\n"
            f"{prefix}资料 营地ID/角色名：角色与赛季资料\n"
            f"{prefix}对局 营地ID/角色名 [序号]：双方对局详情与出装\n"
            f"{prefix}角色查看：查看已保存的角色名称与ID\n"
            f"{prefix}功能：查看本说明\n"
            f"{prefix}营地登录 / {prefix}营地账号：查看账号状态\n"
            "首次查询请在插件管理页微信扫码登录；ID查询成功会自动保存角色名称。\n"
            "战绩、资料、对局可在插件配置中选择图片或文本输出。"
        )
        if self.comment_enabled:
            text += "\n已开启自动锐评：战绩发送成功后会追加一条点评。"
        await event.send(event.plain_result(text))

    async def cmd_battle(
        self, event: AstrMessageEvent, name: str = "", limit: int = 0
    ) -> None:
        """战绩 [营地ID/别名] [场数]。"""
        if not name:
            await event.send(
                event.plain_result(
                    "请提供营地 ID 或角色别名，例如：战绩 123456789\n"
                    "使用营地 ID 查询成功后会自动保存游戏角色名称。"
                )
            )
            return
        result = await self.sender.run(
            event,
            lambda: self.service.battle_report(name, limit=limit or self.default_limit),
            style=self.query_output,
        )
        if self.comment_enabled and result and result.get("code") == 200:
            await self.sender.comment_battle(
                event,
                result,
                context=self.context,
                provider_id=self.comment_provider,
                instructions=self.comment_prompt,
            )

    async def cmd_profile(self, event: AstrMessageEvent, name: str = "") -> None:
        """资料 [营地ID/别名]。"""
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID 或角色别名，例如：资料 123456789")
            )
            return
        await self.sender.run(
            event,
            lambda: self.service.player_overview(name),
            style=self.query_output,
        )

    async def cmd_detail(
        self, event: AstrMessageEvent, name: str = "", index: int = 1
    ) -> None:
        """对局 [营地ID/别名] [序号]。"""
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID 或角色别名，例如：对局 123456789 1")
            )
            return
        await self.sender.run(
            event,
            lambda: self.service.battle_detail(name, index),
            style=self.query_output,
        )

    async def cmd_alias_list(self, event: AstrMessageEvent) -> None:
        """角色查看。"""
        await self.sender.plain(event, await self.service.list_aliases())

    async def cmd_login(self, event: AstrMessageEvent) -> None:
        """营地登录：查看登录状态与扫码入口。"""
        summary = await self.service.account_summary()
        if summary["logged_in"]:
            await event.send(
                event.plain_result(
                    "王者营地登录态正常\n"
                    f"账号：{summary['nickname'] or summary['user_id']}\n"
                    f"可用账号：{summary['available_count']}/{summary['count']}\n"
                    "如需更换账号，请到 AstrBot 管理面板 → 插件 → 王者营地查询 页面扫码。"
                )
            )
            return
        await event.send(
            event.plain_result(
                "尚未登录王者营地，或登录态已失效；也可能账号都在冷却中。\n"
                "请打开 AstrBot 管理面板 → 插件 → 王者营地查询，"
                "点击「获取登录二维码」并用微信扫码登录。"
            )
        )

    async def cmd_accounts(self, event: AstrMessageEvent) -> None:
        """营地账号：列出已登录账号与冷却状态。"""
        summary = await self.service.account_summary()
        accounts = summary.get("accounts") or []
        if not accounts:
            await event.send(
                event.plain_result(
                    "还没有登录任何营地账号，请到插件页面扫码登录后再试。"
                )
            )
            return

        lines = [
            f"已登录营地账号 {summary['count']} 个（可用 {summary['available_count']} 个）"
        ]
        for item in accounts:
            if item.get("auth_invalid"):
                state = "登录态已失效，请重新扫码"
            elif not item.get("ready"):
                state = "登录态不完整，建议重新扫码"
            elif item.get("available"):
                state = "可用"
            else:
                remaining = int(item.get("cooled_remaining") or 0)
                state = f"冷却中（剩余 {remaining // 60} 分 {remaining % 60} 秒）"
            lines.append(
                f"· {item.get('nickname')}（ID {item.get('user_id')}）— {state}"
            )
        await event.send(event.plain_result("\n".join(lines)))
