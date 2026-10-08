"""插件页面路由装配；每类功能由独立模块实现。"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context

from .webui_accounts import WebAccountRoutes
from .webui_aliases import WebAliasRoutes
from .webui_analysis import WebAnalysisRoutes
from .webui_login import WebLoginRoutes
from .webui_queries import WebQueryRoutes

__all__ = ["WebUIService"]


class WebUIService(
    WebLoginRoutes, WebAccountRoutes, WebQueryRoutes, WebAliasRoutes, WebAnalysisRoutes
):
    """保持宿主注册和既有调用入口稳定的页面 API。"""

    def register(self, context: Context, plugin_name: str) -> None:
        routes: tuple[tuple[str, Any, list[str], str], ...] = (
            ("dashboard", self.dashboard, ["GET"], "读取插件总览数据"),
            ("login/status", self.login_status, ["GET"], "读取进行中的扫码会话"),
            ("login/qrcode", self.login_qrcode, ["POST"], "创建微信或 QQ 扫码登录会话"),
            ("login/poll", self.login_poll, ["POST"], "轮询扫码登录状态"),
            ("login/cancel", self.login_cancel, ["POST"], "取消扫码登录会话"),
            ("accounts/delete", self.accounts_delete, ["POST"], "删除营地账号"),
            ("accounts/clear", self.accounts_clear, ["POST"], "清空所有营地账号"),
            ("accounts/check", self.accounts_check, ["POST"], "逐个验证营地登录态"),
            ("query", self.query_player, ["GET"], "按营地ID或别名查询玩家"),
            ("analysis/start", self.analysis_start, ["POST"], "启动所选对局的 AI 分析"),
            (
                "analysis/status",
                self.analysis_status,
                ["GET"],
                "读取 AI 分析进度和结果",
            ),
            ("aliases/list", self.aliases_list, ["GET"], "列出角色别名"),
            ("aliases/update", self.aliases_update, ["POST"], "设置或清除角色别名"),
            ("aliases/delete", self.aliases_delete, ["POST"], "删除角色别名"),
        )
        for path, handler, methods, description in routes:
            context.register_web_api(
                f"/{plugin_name}/{path}", handler, methods, description
            )
        logger.debug("已注册 %d 个插件页面接口", len(routes))
