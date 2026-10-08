"""角色别名页面路由。"""

from __future__ import annotations

from astrbot.api.web import error_response, json_response, request

from .webui_common import WebRoutes


class WebAliasRoutes(WebRoutes):
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
