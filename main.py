"""王者荣耀数据查询工具入口。

数据来源是王者营地官方接口（`kohcamp.qq.com`）：先在插件页面用微信或 QQ 扫码登录，
再用登录态查询玩家数据，不再依赖任何第三方数据接口。

本文件只负责「装配 + 分发」：协议与业务逻辑在 `core/`，Web 接口在 `core/webui.py`，
渲染模板在 `templates/`，插件页面在 `pages/`。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator
from pathlib import Path
from sys import maxsize
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.session_waiter import (
    SessionController,
    SessionFilter,
    session_waiter,
)

from .core.analysis import BattleAnalysisService
from .core.analysis_data import (
    DEFAULT_ANALYSIS_PROMPT,
    PREVIOUS_DEFAULT_ANALYSIS_PROMPT,
)
from .core.camp_api import CampDataApi
from .core.camp_auth import CampAuthStore
from .core.camp_client import CampClient
from .core.camp_login import CampLoginManager
from .core.heroes import hero_repository
from .core.http import HttpClient
from .core.message import MessageSender
from .core.service import GokService
from .core.sqlite import AsyncSQLiteDB
from .core.storage import GokStorage
from .core.subscriptions import SubscriptionService
from .core.webui import WebUIService

PLUGIN_NAME = "astrbot_plugin_gok"
PLAYER_SELECTION_TIMEOUT = 60


class PlayerSelectionFilter(SessionFilter):
    """按会话与发送人隔离候选选择。"""

    def filter(self, event: AstrMessageEvent) -> str:
        """构造会话与发送人共同确定的等待标识。

        Args:
            event: 当前消息事件。

        Returns:
            按当前会话与发送人隔离的等待标识。
        """
        return f"gok-select:{event.unified_msg_origin}:{event.get_sender_id()}"


@register(
    PLUGIN_NAME,
    "飞翔大野猪",
    "营地直连查询、AI 分析缓存与上下线/战绩订阅推送（微信或 QQ 扫码登录）",
    "2.5.2",
    "https://github.com/qsc20001102/astrbot_plugin_gok",
)
class GokPlugin(Star):
    """Camp queries, aliases, persistent AI analysis and subscription push.

    首次使用需在 AstrBot 管理面板的插件页面用微信或 QQ 扫码登录王者营地。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.conf: Any = config or {}

        # 指令表先置空，保证 initialize 完成前的消息处理是安全的
        self.command_map: dict[str, Any] = {}
        self._selection_tasks: set[asyncio.Task] = set()
        self._pending_choices: set[str] = set()

        self._setup_config()
        self._setup_paths()
        self._create_components()

        # 注册插件页面接口（页面本体由宿主自动发现 pages/ 目录）
        self.webui.register(context, PLUGIN_NAME)

        logger.info(
            "GOK 插件已初始化（前缀：%s · 实时查询 / AI 缓存 / 订阅推送 · 英雄目录 %d 条）",
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

        # 只升级原样保存的旧默认提示词，用户自定义的分析要求保持原样。
        analysis = self.conf.get("analysis", {}) or {}
        if (
            str(analysis.get("prompt") or "").strip()
            == PREVIOUS_DEFAULT_ANALYSIS_PROMPT
        ):
            analysis["prompt"] = DEFAULT_ANALYSIS_PROMPT
            save_config = getattr(self.conf, "save_config", None)
            if callable(save_config):
                try:
                    save_config()
                except OSError as exc:
                    logger.warning(
                        "默认分析提示词已更新，配置保存失败：%s", type(exc).__name__
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
        self.analysis = BattleAnalysisService(self.service, self.context, self.conf)
        self.subscriptions = SubscriptionService(self.service, self.context, self.conf)
        self.webui = WebUIService(self.service, self.analysis, self.subscriptions)

    # ------------------------------------------------------------------ 生命周期
    async def initialize(self) -> None:
        """实例化后由框架调用：连库、建表、补齐登录态字段。"""
        try:
            await self.db.connect()
            await self.storage.initialize()
            await self.auth_store.ensure_user_keys()
            await self.analysis.initialize()
            await self.subscriptions.initialize()
        except Exception:
            logger.exception("GOK 插件初始化失败")
            raise

        self._ini_command_map()

        summary = await self.auth_store.summary()
        if summary["logged_in"]:
            logger.info("营地登录态就绪：%s", summary["nickname"])
        else:
            logger.warning(
                "尚未登录王者营地，请在 AstrBot 管理面板 → 插件 → 王者荣耀数据查询工具 页面扫码登录"
            )
        logger.info("GOK 异步初始化完成")

    async def terminate(self) -> None:
        """插件卸载/停用时释放资源。"""
        selection_tasks = tuple(self._selection_tasks)
        for task in selection_tasks:
            task.cancel()
        if selection_tasks:
            await asyncio.gather(*selection_tasks, return_exceptions=True)
        self._selection_tasks.clear()
        self._pending_choices.clear()
        if getattr(self, "subscriptions", None) is not None:
            await self.subscriptions.close()
        if getattr(self, "analysis", None) is not None:
            await self.analysis.close()
        if getattr(self, "login", None) is not None:
            await self.login.close()
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
            # 查询
            "战绩": self.cmd_battle,
            "排位战绩": self.cmd_battle,
            "巅峰战绩": self.cmd_battle,
            "资料": self.cmd_profile,
            "对局": self.cmd_detail,
            "分析": self.cmd_analysis,
            "订阅战绩": self.cmd_subscribe_battle,
            "订阅状态": self.cmd_subscribe_status,
            "查看订阅": self.cmd_subscriptions,
            "取消订阅": self.cmd_unsubscribe,
            # 角色别名
            "角色": self.cmd_alias_list,
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
    async def _resolve_query_player(
        self, event: AstrMessageEvent, name: str
    ) -> str | None:
        """解析玩家输入，同名结果由用户选择。

        Args:
            event: 当前消息事件。
            name: 用户输入的昵称或人工别名。

        Returns:
            可继续查询的玩家标识；取消或失败时为空。
        """
        camp_id, error = await self.service.require_camp_id(name)
        if camp_id is not None:
            return str(camp_id)
        candidates = (error or {}).get("data", {}).get("candidates", [])
        if not candidates:
            await self.sender.plain(event, error or self.service.err("未找到用户"))
            return None
        session_filter = PlayerSelectionFilter()
        session_id = session_filter.filter(event)
        if session_id in self._pending_choices:
            await event.send(
                event.plain_result("已有待选择的查询，请先回复序号或发送取消")
            )
            return None
        self._pending_choices.add(session_id)
        selected: str | None = None

        @session_waiter(timeout=PLAYER_SELECTION_TIMEOUT, record_history_chains=False)
        async def choose(controller: SessionController, reply: AstrMessageEvent):
            """处理编号回复，并保持原始选择截止时间。

            Args:
                controller: 本次候选选择的会话控制器。
                reply: 用户对候选列表的回复消息。

            Returns:
                回复处理结果，不延长等待截止时间。
            """
            nonlocal selected
            reply.should_call_llm(True)
            text = reply.message_str.strip()
            if text in {"取消", "退出"}:
                controller.stop()
                await reply.send(reply.plain_result("已取消查询"))
                return
            if (
                not text.isascii()
                or not text.isdigit()
                or not 1 <= int(text) <= len(candidates)
            ):
                await reply.send(
                    reply.plain_result(f"请回复 1~{len(candidates)} 的序号，或发送取消")
                )
                return
            selected = str(candidates[int(text) - 1]["uid"])
            controller.stop()

        task = asyncio.create_task(choose(event, session_filter=session_filter))
        self._selection_tasks.add(task)
        try:
            # 先注册等待器再发送提示，避免用户立即回复时丢失选择。
            await asyncio.sleep(0)
            lines = [f"「{name}」有 {len(candidates)} 个匹配用户："]
            for index, user in enumerate(candidates, 1):
                details = " · ".join(
                    str(user.get(key) or "")
                    for key in ("region", "dw")
                    if user.get(key)
                )
                alias = f" · 别名 {user['alias']}" if user.get("alias") else ""
                lines.append(
                    f"{index}. {user.get('name') or '未知角色'} · 营地 ID {user['uid']}{alias}"
                    + (f" · {details}" if details else "")
                )
            lines.append(
                f"请在 {PLAYER_SELECTION_TIMEOUT} 秒内回复序号；发送“取消”结束查询。"
            )
            await event.send(event.plain_result("\n".join(lines)))
            await task
        except TimeoutError:
            await event.send(
                event.plain_result("选择已超时，本次查询已结束，请重新发送查询指令")
            )
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._selection_tasks.discard(task)
            self._pending_choices.discard(session_id)
        return selected

    async def cmd_helps(self, event: AstrMessageEvent) -> None:
        """Send help using the configured text or image output.

        Args:
            event: Current conversation.

        Returns:
            None.
        """
        prefix = self.prefix_text if self.prefix_enabled else ""
        text = (
            "王者荣耀数据查询工具\n"
            f"{prefix}战绩 营地ID/别名/昵称 [场数]：全部模式战绩\n"
            f"{prefix}排位战绩 营地ID/别名/昵称 [场数]：排位战绩\n"
            f"{prefix}巅峰战绩 营地ID/别名/昵称 [场数]：巅峰战绩\n"
            f"{prefix}资料 营地ID/角色名：角色、游戏状态与赛季资料\n"
            f"{prefix}对局 营地ID/角色名 [序号]：双方对局详情与出装\n"
            f"{prefix}分析 营地ID/角色名 [序号]：AI 分析本场胜负原因\n"
            f"{prefix}角色：游戏昵称、营地ID与别名\n"
            f"{prefix}订阅状态 营地ID/别名：向当前会话推送上下线\n"
            f"{prefix}订阅战绩 营地ID/别名：向当前会话推送最新已完成对局\n"
            f"{prefix}查看订阅：查看当前会话订阅和完整会话ID\n"
            f"{prefix}取消订阅 营地ID/别名 [状态/战绩/全部]：取消当前会话订阅\n"
            f"{prefix}功能：查看本说明\n"
            f"{prefix}营地登录 / {prefix}营地账号：查看账号状态\n"
            "名称先匹配别名、再匹配游戏昵称，库中没有时在线搜索；多结果回复序号选择。\n"
            "查询成功会自动保存营地 ID 与真实游戏昵称；人工别名在管理页设置。\n"
            "战绩、资料、对局、角色、功能可在插件配置中选择图片或文本输出。\n"
            "订阅只推送最新变化，不补推中间缺失战绩；未关联会话的订阅暂停轮询。"
        )
        result = self.service.ok(
            {"text": text, "prefix": prefix, "battle_limit": self.default_limit},
            temp="helps.html",
        )
        if self.query_output == "image":
            await self.sender.image_only(event, result)
        else:
            await event.send(event.plain_result(text))

    async def cmd_battle(
        self, event: AstrMessageEvent, name: str = "", limit: int = 0
    ) -> None:
        """战绩 [营地ID/别名] [场数]。"""
        if not name:
            await event.send(
                event.plain_result(
                    "请提供营地 ID、别名或昵称，例如：战绩 123456789\n"
                    "查询成功后会自动保存营地 ID 和真实游戏昵称。"
                )
            )
            return
        command = (self.resolve_command(event) or ("战绩", [], None))[0]
        option = {"排位战绩": 1, "巅峰战绩": 4}.get(command, 0)
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is None:
            return
        await self.sender.run(
            event,
            lambda: self.service.battle_report(
                camp_id, limit=limit or self.default_limit, option=option
            ),
            style=self.query_output,
        )

    async def cmd_profile(self, event: AstrMessageEvent, name: str = "") -> None:
        """资料 [营地ID/别名]。"""
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID、别名或昵称，例如：资料 123456789")
            )
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is None:
            return
        await self.sender.run(
            event,
            lambda: self.service.player_overview(camp_id),
            style=self.query_output,
        )

    async def cmd_detail(
        self, event: AstrMessageEvent, name: str = "", index: int = 1
    ) -> None:
        """对局 [营地ID/别名] [序号]。"""
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID、别名或昵称，例如：对局 123456789 1")
            )
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is None:
            return
        await self.sender.run(
            event,
            lambda: self.service.battle_detail(camp_id, index),
            style=self.query_output,
        )

    async def cmd_analysis(
        self, event: AstrMessageEvent, name: str = "", index: int = 1
    ) -> None:
        """分析指定单局，仅发送 AI 结论。

        Args:
            event: 发起分析的聊天消息。
            name: 营地 ID、昵称或别名。
            index: 与对局指令相同的近期对局序号。

        Returns:
            无；通过共用消息层发送分析文字或错误提示。
        """
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID、别名或昵称，例如：分析 489048724 1")
            )
            return
        if index < 1:
            await event.send(event.plain_result("对局序号必须从 1 开始"))
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is None:
            return
        await self.sender.run(
            event, lambda: self.analysis.analyze(camp_id, index), style="text"
        )

    async def cmd_alias_list(self, event: AstrMessageEvent) -> None:
        """角色：按现有输出配置发送角色表格图片或简明文本。"""
        await self.sender.run(event, self.service.list_aliases, style=self.query_output)

    async def cmd_subscribe_status(
        self, event: AstrMessageEvent, name: str = ""
    ) -> None:
        """Subscribe the current conversation to online/offline changes.

        Args:
            event: Current conversation.
            name: Camp ID, nickname or alias.

        Returns:
            None.
        """
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID 或别名，例如：订阅状态 123456789")
            )
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is not None:
            await self.sender.run(
                event,
                lambda: self.subscriptions.subscribe(
                    "status", camp_id, event.unified_msg_origin
                ),
            )

    async def cmd_subscribe_battle(
        self, event: AstrMessageEvent, name: str = ""
    ) -> None:
        """Subscribe the current conversation to its player's latest completed match.

        Args:
            event: Current conversation.
            name: Camp ID, nickname or alias.

        Returns:
            None.
        """
        if not name:
            await event.send(
                event.plain_result("请提供营地 ID 或别名，例如：订阅战绩 123456789")
            )
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is not None:
            await self.sender.run(
                event,
                lambda: self.subscriptions.subscribe(
                    "battle", camp_id, event.unified_msg_origin
                ),
            )

    async def cmd_subscriptions(self, event: AstrMessageEvent) -> None:
        """List the current conversation's subscriptions and full session ID.

        Args:
            event: Current conversation.

        Returns:
            None.
        """
        await self.sender.run(
            event, lambda: self.subscriptions.list_session(event.unified_msg_origin)
        )

    async def cmd_unsubscribe(
        self, event: AstrMessageEvent, name: str = "", category: str = "全部"
    ) -> None:
        """Remove status, battle or both subscriptions from this conversation.

        Args:
            event: Current conversation.
            name: Camp ID, nickname or alias.
            category: 状态, 战绩 or 全部.

        Returns:
            None.
        """
        if not name:
            await event.send(
                event.plain_result(
                    "请提供营地 ID 或别名，例如：取消订阅 123456789 [状态/战绩/全部]"
                )
            )
            return
        if category not in {"状态", "战绩", "全部"}:
            await event.send(
                event.plain_result("取消类型请选择「状态」「战绩」或「全部」")
            )
            return
        camp_id = await self._resolve_query_player(event, name)
        if camp_id is not None:
            kind = {"状态": "status", "战绩": "battle", "全部": ""}[category]
            await self.sender.run(
                event,
                lambda: self.subscriptions.unsubscribe(
                    camp_id, event.unified_msg_origin, kind
                ),
            )

    async def cmd_login(self, event: AstrMessageEvent) -> None:
        """营地登录：查看登录状态与扫码入口。"""
        summary = await self.service.account_summary()
        if summary["logged_in"]:
            await event.send(
                event.plain_result(
                    "王者营地登录态正常\n"
                    f"账号：{summary['nickname'] or summary['user_id']}\n"
                    f"可用账号：{summary['available_count']}/{summary['count']}\n"
                    "如需更换账号，请到 AstrBot 管理面板 → 插件 → 王者荣耀数据查询工具 页面扫码。"
                )
            )
            return
        await event.send(
            event.plain_result(
                "尚未登录王者营地，或登录态已失效；也可能账号都在冷却中。\n"
                "请打开 AstrBot 管理面板 → 插件 → 王者荣耀数据查询工具，"
                "在「账号管理」中选择微信或 QQ，点击「获取二维码」扫码登录。"
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
