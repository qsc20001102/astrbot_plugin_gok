"""插件 Web 页面后端：扫码登录、账号管理、玩家查询、别名管理。

页面在 AstrBot 管理端的 iframe 中打开，通过宿主注入的 bridge
（`window.AstrBotPluginPage.apiGet/apiPost`）调用这里的路由；路由统一以
`/{插件名}/` 前缀注册，鉴权由宿主 dashboard 登录态负责。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.api.web import error_response, json_response, request

from .camp_auth import CampAccount
from .service import GokService

__all__ = ["WebUIService"]


class WebUIService:
    """插件页面 API。"""

    def __init__(self, service: GokService) -> None:
        self.service = service

    # ------------------------------------------------------------------ 注册
    def register(self, context: Context, plugin_name: str) -> None:
        routes: tuple[tuple[str, Any, list[str], str], ...] = (
            ("dashboard", self.dashboard, ["GET"], "读取插件总览数据"),
            ("login/status", self.login_status, ["GET"], "读取进行中的扫码会话"),
            ("login/qrcode", self.login_qrcode, ["POST"], "创建微信扫码登录会话"),
            ("login/poll", self.login_poll, ["POST"], "轮询扫码登录状态"),
            ("login/cancel", self.login_cancel, ["POST"], "取消扫码登录会话"),
            ("accounts/delete", self.accounts_delete, ["POST"], "删除营地账号"),
            ("accounts/clear", self.accounts_clear, ["POST"], "清空所有营地账号"),
            ("accounts/check", self.accounts_check, ["POST"], "逐个验证营地登录态"),
            ("query", self.query_player, ["GET"], "按营地ID或别名查询玩家"),
            ("aliases/list", self.aliases_list, ["GET"], "列出角色别名"),
            ("aliases/update", self.aliases_update, ["POST"], "设置或清除角色别名"),
            ("aliases/delete", self.aliases_delete, ["POST"], "删除角色别名"),
        )
        for path, handler, methods, description in routes:
            context.register_web_api(
                f"/{plugin_name}/{path}", handler, methods, description
            )
        logger.debug("已注册 %d 个插件页面接口", len(routes))

    # ------------------------------------------------------------------ 工具
    @staticmethod
    async def _payload() -> dict[str, Any]:
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            raise ValueError("请求正文必须是 JSON 对象")
        return payload

    @staticmethod
    def _str_param(payload: dict[str, Any], key: str, default: str = "") -> str:
        value = payload.get(key, default)
        return str(value).strip() if value is not None else default

    @staticmethod
    def _int_param(payload: dict[str, Any], key: str, default: int = 0) -> int:
        try:
            return int(payload.get(key, default))
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------ 总览
    async def dashboard(self):
        """账号状态 + 角色别名 + 活动中的扫码会话（不含任何数据缓存）。"""
        try:
            accounts = await self.service.account_summary()
            stats = await self.service.local_stats()
            aliases = await self.service.storage.list_aliases()
            sessions = [
                {
                    "task_id": s.task_id,
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

    # ------------------------------------------------------------------ 扫码登录
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
                "qrcode_base64": session.qrcode_base64,
                "qrcode_mime": session.qrcode_mime,
                "expires_in": session.remaining_seconds,
            }
        )

    async def login_qrcode(self):
        """创建一次扫码会话并返回二维码（微信返回的是 JPEG）。"""
        try:
            session, error = await self.service.login.create_session()
            if session is None:
                return error_response(error or "获取登录二维码失败", status_code=400)
            return json_response(
                {
                    "task_id": session.task_id,
                    "qrcode_base64": session.qrcode_base64,
                    "qrcode_mime": session.qrcode_mime,
                    "expires_in": session.remaining_seconds,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("创建扫码会话失败")
            return error_response(
                f"创建扫码会话失败：{type(exc).__name__}", status_code=500
            )

    async def login_poll(self):
        """Return login status after the manager has saved the credentials.

        Returns:
            Login outcome and a public account summary on success.
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
        return json_response(
            {
                "status": status,
                "message": result.get("message", ""),
                "terminal": bool(result.get("terminal")),
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

    # ------------------------------------------------------------------ 账号
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
        """Validate each account independently and return public outcomes.

        Returns:
            Counts and per-account outcomes, without login credentials.
        """
        try:
            return json_response(await self.service.api.client.validate_accounts())
        except Exception as exc:  # noqa: BLE001
            logger.exception("检测营地登录态失败")
            return error_response(
                f"检测登录态失败({type(exc).__name__})，请稍后重试", status_code=500
            )

    # ------------------------------------------------------------------ 查询
    async def query_player(self):
        """网页版查询：type = profile | battle | detail。"""
        query = request.query
        keyword = str(query.get("keyword", "") or "").strip()
        kind = str(query.get("type", "battle") or "battle").strip().lower()
        # PluginMultiDict.get 原生支持 type= 转换，转换失败自动回退默认值
        limit = query.get("limit", 10, type=int)
        index = query.get("index", 1, type=int)
        game_seq = str(query.get("game_seq", "") or "").strip()
        option = query.get("option", 0, type=int)
        if option not in (0, 1, 4):
            return error_response("option 只支持 0 / 1 / 4", status_code=400)

        if not keyword:
            return error_response("请提供营地 ID 或别名", status_code=400)
        if kind not in {"profile", "battle", "detail"}:
            return error_response(
                "type 只支持 profile / battle / detail", status_code=400
            )

        try:
            # 不做缓存，每次查询都实时请求营地接口
            if kind == "profile":
                result = await self.service.player_overview(keyword)
            elif kind == "detail":
                result = await self.service.battle_detail(
                    keyword, index, game_seq=game_seq
                )
            else:
                result = await self.service.battle_report(
                    keyword, limit=limit, option=option
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("网页查询失败")
            return error_response(f"查询失败：{type(exc).__name__}", status_code=500)

        if result.get("code") != 200:
            candidates = result.get("data", {}).get("candidates")
            if candidates:
                return json_response(
                    {
                        "status": "ok",
                        "data": {
                            "type": "selection",
                            "query_type": kind,
                            "keyword": keyword,
                            "option": option,
                            "data": {"candidates": candidates},
                        },
                    }
                )
            return error_response(str(result.get("msg") or "查询失败"), status_code=400)
        # The host unwraps top-level data; keep metadata inside an explicit envelope.
        return json_response(
            {
                "status": "ok",
                "data": {"type": kind, "keyword": keyword, "data": result.get("data")},
            }
        )

    # ------------------------------------------------------------------ 别名
    async def aliases_list(self):
        keyword = str(request.query.get("keyword", "") or "").strip()
        if keyword:
            result = await self.service.search_aliases(keyword)
        else:
            result = await self.service.list_aliases()
        if result.get("code") != 200:
            return json_response({"list": [], "message": result.get("msg", "")})
        return json_response(result.get("data") or {})

    async def aliases_update(self):
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        gokid = self._int_param(payload, "gokid")
        if "alias" not in payload:
            return error_response("请提供别名，留空可清除别名", status_code=400)
        if any(key in payload for key in ("name", "role_name", "camp_id")):
            return error_response(
                "营地 ID 和游戏昵称不可修改，只能设置别名", status_code=400
            )
        name = self._str_param(payload, "alias")
        if not gokid:
            return error_response("请提供营地 ID", status_code=400)
        result = await self.service.update_alias(gokid, name)
        if result.get("code") != 200:
            return error_response(str(result.get("msg")), status_code=400)
        return json_response({"updated": True})

    async def aliases_delete(self):
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        gokid = self._int_param(payload, "gokid")
        if not gokid:
            return error_response("请提供营地 ID", status_code=400)
        result = await self.service.delete_alias(gokid)
        if result.get("code") != 200:
            return error_response(str(result.get("msg")), status_code=404)
        return json_response({"deleted": True})
