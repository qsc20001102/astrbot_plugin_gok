"""页面路由共用的服务依赖与参数读取。"""

from __future__ import annotations

from typing import Any

from astrbot.api.web import request

from .analysis import BattleAnalysisService
from .service import GokService


class WebRoutes:
    def __init__(
        self, service: GokService, analysis: BattleAnalysisService | None = None
    ) -> None:
        self.service = service
        self.analysis = analysis

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
