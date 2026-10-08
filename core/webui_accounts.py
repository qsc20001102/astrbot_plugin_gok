"""账号管理与页面总览路由。"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.web import error_response, json_response

from .webui_common import WebRoutes


class WebAccountRoutes(WebRoutes):
    async def dashboard(self):
        """账号状态 + 角色别名 + 活动中的扫码会话（不含任何数据缓存）。"""
        try:
            accounts = await self.service.account_summary()
            stats = await self.service.local_stats()
            aliases = await self.service.storage.list_aliases()
            sessions = [
                {
                    "task_id": s.task_id,
                    "platform": s.platform,
                    "remaining_seconds": s.remaining_seconds,
                    "qrcode_base64": s.qrcode_base64,
                    "qrcode_mime": s.qrcode_mime,
                }
                for s in self.service.login.list_sessions()
            ]
            return json_response(
                {
                    "accounts": accounts,
                    "stats": stats,
                    "aliases": aliases,
                    "sessions": sessions,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("读取插件总览失败")
            return error_response(
                f"读取总览失败：{type(exc).__name__}", status_code=500
            )

    async def accounts_delete(self):
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        user_id = self._str_param(payload, "user_id")
        if not user_id:
            return error_response("缺少 user_id", status_code=400)
        try:
            if not await self.service.auth_store.remove(user_id):
                return error_response("没有找到该营地账号", status_code=404)
        except OSError:
            logger.exception("删除营地账号失败")
            return error_response(
                "删除账号失败，请检查插件数据目录写入权限", status_code=500
            )
        return json_response({"deleted": True})

    async def accounts_clear(self):
        try:
            await self.service.auth_store.clear()
        except OSError:
            logger.exception("清空营地账号失败")
            return error_response(
                "清空账号失败，请检查插件数据目录写入权限", status_code=500
            )
        return json_response({"cleared": True})

    async def accounts_check(self):
        """逐个验证账号并返回不含凭据的公开结果。

        Returns:
            各账号的公开检测结果。
        """
        try:
            return json_response(await self.service.api.client.validate_accounts())
        except Exception as exc:  # noqa: BLE001
            logger.exception("检测营地登录态失败")
            return error_response(
                f"检测登录态失败({type(exc).__name__})，请稍后重试", status_code=500
            )
