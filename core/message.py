"""消息发送层：把业务结果渲染成图片或文本发到会话。

业务层只返回 `{"code", "msg", "data", "temp"}`，这里统一决定怎么发：
`temp` 有值就渲图，否则发文本。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from .template import load_template, secure_render_template
from .text_formatters import format_service_text

__all__ = ["MessageSender"]

ServiceResult = dict[str, Any]
ActionResult = Callable[[], Awaitable[ServiceResult]]

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class MessageSender:
    """统一的消息发送与图片渲染。"""

    # 渲染清晰度档位
    _SCALE_LEVELS = {"1.0": "normal", "1.3": "high", "1.8": "ultra"}

    def __init__(
        self, render_config: dict[str, Any] | None = None, plugin: Any = None
    ) -> None:
        self.render_config = render_config if isinstance(render_config, dict) else {}
        self.plugin = plugin

    # ------------------------------------------------------------------ 渲染参数
    def build_render_options(
        self, overrides: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        fmt = str(self.render_config.get("format", "jpeg")).lower()
        if fmt not in {"jpeg", "png"}:
            fmt = "jpeg"
        try:
            quality = max(1, min(100, int(self.render_config.get("jpeg_quality", 100))))
        except (TypeError, ValueError):
            quality = 100
        scale = str(self.render_config.get("device_scale_factor", "1.3"))
        options: dict[str, Any] = {
            "quality": quality,
            "device_scale_factor_level": self._SCALE_LEVELS.get(scale, "high"),
            "scale": "device",
            "full_page": True,
            "omit_background": False,
            "type": fmt,
        }
        options.update(overrides or {})
        if options.get("type") == "png":
            options.pop("quality", None)
        return options

    async def render(self, template: str, data: dict[str, Any], **kwargs: Any) -> str:
        """渲染模板为图片，返回 URL 或本地路径。"""
        if self.plugin is None:
            raise RuntimeError("MessageSender 未绑定插件实例，无法渲染")
        source = await load_template(template)
        return await self.plugin.html_render(
            secure_render_template(source), data, **kwargs
        )

    @staticmethod
    def now_text() -> str:
        return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------ 发送方式
    async def plain(self, event: AstrMessageEvent, result: ServiceResult) -> None:
        """发纯文本。"""
        await event.send(event.plain_result(self._text_of(result)))

    _text_of = staticmethod(format_service_text)

    async def text_and_image(
        self, event: AstrMessageEvent, result: ServiceResult
    ) -> None:
        """文本说明 + 渲染图（文本在有意义时才发）。"""
        if result.get("code") != 200:
            await event.send(event.plain_result(self._text_of(result)))
            return
        template = result.get("temp")
        if not template:
            await event.send(event.plain_result(self._text_of(result)))
            return
        try:
            image = await self.render(
                template,
                {
                    "data": result.get("data") or {},
                    "data_time": self.now_text(),
                },
                return_url=True,
                options=self.build_render_options(),
            )
            await event.send(event.image_result(image))
        except Exception as exc:  # noqa: BLE001 - 渲染失败要降级为文本
            logger.exception("模板渲染失败: %s", template)
            await event.send(
                event.plain_result(
                    f"图片渲染失败（{type(exc).__name__}），以下为文本结果：\n{self._text_of(result)}"
                )
            )

    async def image_only(self, event: AstrMessageEvent, result: ServiceResult) -> None:
        """只发渲染图，失败时降级为文本。"""
        await self.text_and_image(event, result)

    async def run(
        self,
        event: AstrMessageEvent,
        action: ActionResult,
        *,
        style: str = "text",
    ) -> ServiceResult | None:
        """执行动作并按指定风格发送，返回业务结果。"""
        try:
            result = await action()
        except Exception as exc:  # noqa: BLE001 - 兜底，避免异常穿透到分发层
            logger.exception("业务动作执行失败")
            await event.send(
                event.plain_result(f"处理失败（{type(exc).__name__}），请稍后再试")
            )
            return None

        if style == "image":
            await self.image_only(event, result)
        elif style == "chain":
            await self.chain(event, result)
        else:
            await self.plain(event, result)
        return result

    async def chain(self, event: AstrMessageEvent, result: ServiceResult) -> None:
        """文本 + 附图组成一条消息链；无图时退化为纯文本。"""
        if result.get("code") != 200 or not result.get("temp"):
            await event.send(event.plain_result(self._text_of(result)))
            return
        try:
            path = await self.render(
                result["temp"],
                {"data": result.get("data") or {}, "data_time": self.now_text()},
                return_url=False,
                options=self.build_render_options(),
            )
            chain = MessageChain()
            text = self._text_of(result)
            if text and text != "查询完成":
                chain.message(text)
            chain.file_image(str(path))
            await event.send(chain)
        except Exception as exc:  # noqa: BLE001
            logger.exception("消息链发送失败")
            await event.send(event.plain_result(f"发送失败（{type(exc).__name__}）"))
