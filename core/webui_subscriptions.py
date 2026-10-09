"""Management page routes for subscription targets and session routing."""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.web import error_response, json_response

from .webui_common import WebRoutes


class WebSubscriptionRoutes(WebRoutes):
    async def subscriptions_list(self):
        """Read current subscription snapshots and scheduler activity.

        Returns:
            Subscription system overview or a readable service error.
        """
        if self.subscriptions is None:
            return error_response("订阅服务尚未就绪，请重新加载插件", status_code=503)
        try:
            data = await self.subscriptions.overview()
            return json_response({"status": "ok", "data": data})
        except Exception:  # noqa: BLE001 - Keep database errors out of the response.
            logger.exception("读取订阅系统失败")
            return error_response("读取订阅系统失败，请稍后重试", status_code=500)

    async def subscriptions_update(self):
        """Apply one explicit target or session operation from the management page.

        Returns:
            Updated overview, or an input/storage error.
        """
        if self.subscriptions is None:
            return error_response("订阅服务尚未就绪，请重新加载插件", status_code=503)
        try:
            payload = await self._payload()
            action = self._str_param(payload, "action")
            if action in {"add_target", "delete_target"}:
                kind = self._str_param(payload, "kind")
                camp_id = self._str_param(payload, "camp_id")
                if action == "add_target":
                    await self.subscriptions.add(kind, camp_id)
                else:
                    await self.subscriptions.remove_target(kind, camp_id)
            elif action == "save_session":
                selections = []
                for kind in ("status", "battle"):
                    values = payload.get(f"{kind}_ids", [])
                    if not isinstance(values, list) or any(
                        not isinstance(value, str) for value in values
                    ):
                        raise ValueError("会话订阅必须是营地 ID 字符串列表")
                    selections.extend((kind, value.strip()) for value in values)
                await self.subscriptions.save_session(
                    self._str_param(payload, "session_id"), selections
                )
            elif action == "delete_session":
                session_id = self._str_param(payload, "session_id")
                if not session_id:
                    raise ValueError("请提供要删除的会话 ID")
                await self.subscriptions.remove_session(session_id)
            else:
                raise ValueError("不支持的订阅操作")
            return json_response(
                {"status": "ok", "data": await self.subscriptions.overview()}
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception:  # noqa: BLE001 - Do not report success after failed storage.
            logger.exception("修改订阅系统失败")
            return error_response("订阅修改失败，请稍后重试", status_code=500)
