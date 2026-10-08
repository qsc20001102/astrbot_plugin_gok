"""玩家数据查询页面路由。"""

from __future__ import annotations

from astrbot.api import logger
from astrbot.api.web import error_response, json_response, request

from .webui_common import WebRoutes


class WebQueryRoutes(WebRoutes):
    async def query_player(self):
        """网页版查询：type = profile | battle | detail。"""
        query = request.query
        keyword = str(query.get("keyword", "") or "").strip()
        kind = str(query.get("type", "battle") or "battle").strip().lower()
        # PluginMultiDict.get 原生支持 type= 转换，转换失败自动回退默认值
        limit = query.get("limit", 10, type=int)
        limit = min(25, max(1, limit))
        index = query.get("index", 1, type=int)
        game_seq = str(query.get("game_seq", "") or "").strip()
        option = query.get("option", 0, type=int)
        if option not in (0, 1, 4):
            return error_response("option 只支持 0 / 1 / 4", status_code=400)

        if not keyword:
            return error_response("请提供营地 ID 或别名", status_code=400)
        if kind not in {"profile", "battle", "detail", "replay"}:
            return error_response(
                "type 只支持 profile / battle / detail / replay", status_code=400
            )

        try:
            # 不做缓存，每次查询都实时请求营地接口
            if kind == "profile":
                result = await self.service.player_overview(keyword)
            elif kind == "detail":
                result = await self.service.battle_detail(
                    keyword, index, game_seq=game_seq
                )
            elif kind == "replay":
                result = await self.service.battle_replay(
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
        # 宿主会解包顶层 data，因此查询类型与结果放在同一个明确的响应对象中。
        return json_response(
            {
                "status": "ok",
                "data": {"type": kind, "keyword": keyword, "data": result.get("data")},
            }
        )
