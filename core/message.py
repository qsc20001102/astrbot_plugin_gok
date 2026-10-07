"""消息发送层：把业务结果渲染成图片或文本发到会话。

业务层只返回 `{"code", "msg", "data", "temp"}`，这里统一决定怎么发：
`temp` 有值就渲图，否则发文本；锐评在有 LLM 时追加一条消息。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

from .template import load_template, secure_render_template

__all__ = ["MessageSender", "DEFAULT_COMMENT_PROMPT"]

DEFAULT_COMMENT_PROMPT = "请根据提供的王者荣耀最近对局数据，用简短的一句话进行锐评吐槽。要口语化、有梗，不要复述数据。"

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

    @staticmethod
    def _text_of(result: ServiceResult) -> str:
        if result.get("code") == 200:
            data = result.get("data")
            if isinstance(data, str):
                return data
            if isinstance(data, dict) and data.get("text"):
                return str(data["text"])
            if isinstance(data, dict):
                if result.get("temp") == "aliases.html":
                    rows = data.get("list") or []
                    return "已保存角色（游戏昵称 · 营地 ID · 别名）\n" + "\n".join(
                        f"{i}. {row['role_name'] or '待更新昵称'} · {row['gokid']} · 别名：{row['alias'] or '未设置'}"
                        for i, row in enumerate(rows, 1)
                    )
                profile = data.get("profile") or {}
                lines = [
                    f"{profile.get('nickname') or '未知角色'} · 营地 ID {profile.get('camp_id') or '—'}",
                    f"{profile.get('server_name') or profile.get('area_name') or '未知区服'} · {profile.get('rank_label') or '未知段位'} {profile.get('current_stars') or 0}星",
                ]
                if result.get("temp") == "profile.html":
                    lines.extend(
                        [
                            f"本赛季：{profile.get('season_games', 0)}场 / {profile.get('season_wins', 0)}胜 / 胜率 {profile.get('win_rate', 0)}%",
                            f"排位评分：{profile.get('rank_score') or '—'} · 巅峰积分：{profile.get('peak_score') or '—'}",
                        ]
                    )
                    heroes = data.get("season_heroes") or []
                    if heroes:
                        lines.append(
                            "常用英雄："
                            + "；".join(
                                f"{h['hero_name']} {h['games']}场 {h['win_rate']}%"
                                for h in heroes[:5]
                            )
                        )
                    if data.get("hide_match"):
                        lines.append("该角色已隐藏战绩")
                    return "\n".join(lines)
                if result.get("temp") == "battle.html":
                    lines.insert(0, str(data.get("query_title") or "全部战绩"))
                    summary = data.get("summary") or {}
                    lines.append(
                        f"近{summary.get('total', 0)}场：{summary.get('wins', 0)}胜 / {summary.get('loses', 0)}负 / 胜率 {summary.get('win_rate', 0)}%"
                    )
                    for i, match in enumerate(data.get("list") or [], 1):
                        lines.append(
                            f"{i}. {match['played_at']} {match['hero_name']} {match['result_text']} {match['kills']}/{match['deaths']}/{match['assists']} 评分 {match['score_text']}"
                        )
                    return "\n".join(lines)
                if result.get("temp") == "detail.html":
                    match = data.get("match") or {}
                    lines.extend(
                        [
                            f"{match.get('played_at', '')} · {match.get('mode_name', '')} · {match.get('result_text', '')}",
                            f"{match.get('hero_name', '')} {match.get('kills', 0)}/{match.get('deaths', 0)}/{match.get('assists', 0)} · 评分 {match.get('score_text', '—')} · 时长 {match.get('duration_text', '—')}",
                        ]
                    )
                    for label, key in (("蓝方", "blue"), ("红方", "red")):
                        lines.append(label)
                        for role in data.get(key) or []:
                            lines.append(
                                f"{role.get('nickname') or '未知玩家'} · {role.get('hero_name') or '—'} {role.get('kills', 0)}/{role.get('deaths', 0)}/{role.get('assists', 0)}"
                            )
                            equipment = role.get("equipment") or []
                            if equipment:
                                lines.append(
                                    "出装："
                                    + "、".join(
                                        item.get("name") or f"装备{item.get('id', '')}"
                                        for item in equipment
                                    )
                                )
                    return "\n".join(lines)
            return "查询完成"
        return str(result.get("msg") or "查询失败")

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
        """执行动作并按指定风格发送；返回业务结果供上层复用（如锐评）。"""
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

    # ------------------------------------------------------------------ 锐评
    async def comment_battle(
        self,
        event: AstrMessageEvent,
        result: ServiceResult,
        *,
        context: Any,
        provider_id: str = "",
        instructions: str = DEFAULT_COMMENT_PROMPT,
    ) -> None:
        """调用 LLM 对最近战绩做一句锐评。"""
        comment = (result.get("data") or {}).get("comment")
        if not comment:
            return
        try:
            if provider_id:
                target = provider_id
            else:
                target = await context.get_current_chat_provider_id(
                    umo=event.unified_msg_origin
                )
            prompt = (
                f"{instructions.strip() or DEFAULT_COMMENT_PROMPT}\n\n"
                f"对局列表：{json.dumps(comment, ensure_ascii=False)}\n"
                "字段说明：gametime 对局时间，mapName 模式，heroName 英雄，"
                "killcnt 击杀，deadcnt 死亡，assistcnt 助攻，"
                "gameresult 1 胜利 2 失败，mvpcnt 1 表示胜方 MVP，"
                "losemvp 1 表示败方 MVP，gradeGame 系统评分（满分 16），medal 奖牌。"
            )
            response = await context.llm_generate(
                chat_provider_id=target, prompt=prompt
            )
            text = getattr(response, "completion_text", "") or ""
            if text.strip():
                await event.send(event.plain_result(text.strip()))
        except Exception as exc:  # noqa: BLE001 - 锐评失败不影响主查询
            logger.warning("战绩锐评失败：%s", type(exc).__name__)
