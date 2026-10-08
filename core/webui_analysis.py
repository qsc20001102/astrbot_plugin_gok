"""地图回顾的 AI 分析路由，生成过程在后台运行。"""

from __future__ import annotations

from astrbot.api.web import error_response, json_response, request

from .webui_common import WebRoutes


class WebAnalysisRoutes(WebRoutes):
    async def analysis_start(self):
        """启动所选对局的分析，不接受客户端传来的对局数据或提示词。

        Returns:
            临时任务标识或明确的参数 / 配置错误。
        """
        if self.analysis is None:
            return error_response(
                "AI 对局分析服务尚未就绪，请重新加载插件", status_code=503
            )
        try:
            payload = await self._payload()
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        keyword = self._str_param(payload, "keyword")
        game_seq = self._str_param(payload, "game_seq")
        index = self._int_param(payload, "index", 1)
        if not keyword or not game_seq or index < 1:
            return error_response(
                "请提供玩家、所选对局标识和从 1 开始的序号", status_code=400
            )
        result = self.analysis.start(keyword, index, game_seq=game_seq)
        if result.get("code") != 200:
            return error_response(
                str(result.get("msg") or "无法启动分析"), status_code=400
            )
        return json_response({"status": "ok", "data": result["data"]})

    async def analysis_status(self):
        """读取进度与文字结果，不向页面暴露固定提示词或模型输入。

        Returns:
            当前分析状态或任务不存在的错误。
        """
        if self.analysis is None:
            return error_response(
                "AI 对局分析服务尚未就绪，请重新加载插件", status_code=503
            )
        task_id = str(request.query.get("task_id", "") or "").strip()
        result = self.analysis.status(task_id)
        if result.get("code") != 200:
            return error_response(
                str(result.get("msg") or "分析任务不存在"), status_code=404
            )
        return json_response({"status": "ok", "data": result["data"]})
