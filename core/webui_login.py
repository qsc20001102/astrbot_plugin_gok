"""扫码登录页面路由。"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.web import error_response, json_response

from .camp_auth import CampAccount
from .webui_common import WebRoutes


class WebLoginRoutes(WebRoutes):
    async def login_status(self):
        """返回当前仍在有效期内的扫码会话，供页面刷新后恢复二维码与轮询。"""
        try:
            sessions = self.service.login.list_sessions()
        except Exception as exc:  # noqa: BLE001
            logger.exception("读取扫码会话失败")
            return error_response(
                f"读取扫码会话失败：{type(exc).__name__}", status_code=500
            )
        if not sessions:
            return json_response({"active": False})
        session = sessions[0]
        return json_response(
            {
                "active": True,
                "task_id": session.task_id,
                "platform": session.platform,
                "qrcode_base64": session.qrcode_base64,
                "qrcode_mime": session.qrcode_mime,
                "expires_in": session.remaining_seconds,
            }
        )

    async def login_qrcode(self):
        """创建一次扫码会话并返回二维码（微信返回的是 JPEG）。"""
        try:
            payload = await self._payload()
            platform = self._str_param(payload, "platform", "wechat")
            if platform not in {"wechat", "qq"}:
                return error_response("登录方式只支持 wechat / qq", status_code=400)
            session, error = await self.service.login.create_session(platform)
            if session is None:
                return error_response(error or "获取登录二维码失败", status_code=400)
            return json_response(
                {
                    "task_id": session.task_id,
                    "platform": session.platform,
                    "qrcode_base64": session.qrcode_base64,
                    "qrcode_mime": session.qrcode_mime,
                    "expires_in": session.remaining_seconds,
                }
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:  # noqa: BLE001
            logger.exception("创建扫码会话失败")
            return error_response(
                f"创建扫码会话失败：{type(exc).__name__}", status_code=500
            )

    async def login_poll(self):
        """凭据保存后返回登录状态与公开账号摘要。

        Returns:
            登录状态；成功时附带公开账号摘要。
        """
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        task_id = self._str_param(payload, "task_id")
        if not task_id:
            return error_response("缺少 task_id", status_code=400)

        try:
            result = await self.service.login.poll(task_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("轮询扫码状态失败")
            return error_response(f"轮询失败：{type(exc).__name__}", status_code=500)

        status = result.get("status")
        if status == "success":
            account: CampAccount = result["account"]
            logger.info("营地扫码登录成功：%s", account.display_name)
            return json_response(
                {
                    "status": "success",
                    "message": "登录成功",
                    "account": account.public_dict(),
                }
            )
        # The host bridge rejects status=error and discards business terminal flags.
        if status == "error":
            status = "failed" if result.get("terminal") else "retrying"
        return json_response(
            {
                "status": status,
                "message": result.get("message", ""),
                "terminal": bool(result.get("terminal")),
                **{
                    key: result[key]
                    for key in (
                        "platform",
                        "qrcode_base64",
                        "qrcode_mime",
                        "expires_in",
                    )
                    if key in result
                },
            }
        )

    async def login_cancel(self):
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        task_id = self._str_param(payload, "task_id")
        if task_id:
            self.service.login.drop_session(task_id)
        return json_response({"canceled": True})
