"""共用的 AI 对局分析服务，供聊天指令和地图回顾页面调用。"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from typing import Any

from astrbot.api import logger

from .analysis_data import (
    ANALYSIS_DATA_PROMPT,
    DEFAULT_ANALYSIS_PROMPT,
    PREVIOUS_DEFAULT_ANALYSIS_PROMPT,
    build_analysis_data,
)
from .service import GokService, ServiceResult

ANALYSIS_TIMEOUT_SECONDS = 180
JOB_LIFETIME_SECONDS = 900
MAX_ACTIVE_ANALYSES = 3
MAX_JOBS = 32


class BattleAnalysisService:
    """只在显式请求时调用模型，后台任务仅暂存进度和分析结果。"""

    def __init__(self, service: GokService, context: Any, config: Any) -> None:
        self.service = service
        self.context = context
        self.config = config
        self._tasks: set[asyncio.Task] = set()
        self._jobs: dict[str, dict[str, Any]] = {}

    async def analyze(
        self,
        keyword: str,
        index: int = 1,
        *,
        game_seq: str = "",
        job: dict[str, Any] | None = None,
    ) -> ServiceResult:
        """查询同一场的详情与回顾，只返回模型分析文字。

        Args:
            keyword: 营地 ID、昵称或别名。
            index: 近期对局序号，从 1 开始。
            game_seq: 页面选中的对局标识；提供后不回退到另一场。
            job: 页面后台任务状态；聊天调用无需提供。

        Returns:
            成功时 data 为分析文本；失败时 msg 为明确的原因。
        """
        settings = self.config.get("analysis", {}) or {}
        provider = str(settings.get("select_provider") or "").strip()
        instructions = (
            str(settings.get("prompt") or DEFAULT_ANALYSIS_PROMPT).strip()
            or DEFAULT_ANALYSIS_PROMPT
        )
        if instructions == PREVIOUS_DEFAULT_ANALYSIS_PROMPT:
            instructions = DEFAULT_ANALYSIS_PROMPT
        if not provider:
            return self.service.err("请先在插件配置的「AI 对局分析」中选择分析模型")
        task = asyncio.current_task()
        if task not in self._tasks and len(self._tasks) >= MAX_ACTIVE_ANALYSES:
            return self.service.err("当前分析任务较多，请稍后再试")
        if task:
            self._tasks.add(task)
        try:
            async with asyncio.timeout(ANALYSIS_TIMEOUT_SECONDS):
                if job is not None:
                    job.update(status="running", message="正在读取双方对局数据…")
                detail = await self.service.battle_detail(
                    keyword, index, game_seq=game_seq
                )
                if detail.get("code") != 200:
                    return detail
                if job is not None:
                    job["message"] = "正在读取全员轨迹和关键事件…"
                # 复用这次查询的详情与对局标识，不重复获取详情或按新序号取另一场。
                replay = await self.service.battle_replay(
                    keyword,
                    index,
                    game_seq=detail["data"]["match"]["game_seq"],
                    detail_data=detail["data"],
                )
                if replay.get("code") != 200:
                    return replay
                try:
                    data = build_analysis_data(detail["data"], replay["data"])
                except ValueError as exc:
                    return self.service.err(str(exc))
                if job is not None:
                    job["message"] = "正在分析双方表现、轨迹与事件…"
                response = await self.context.llm_generate(
                    chat_provider_id=provider,
                    system_prompt=ANALYSIS_DATA_PROMPT,
                    prompt=f"分析任务：\n{instructions}\n\n对局数据（JSON）：\n{json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)}",
                )
                text = str(getattr(response, "completion_text", "") or "").strip()
                if not text:
                    return self.service.err(
                        "模型没有返回分析内容，请重试或检查模型配置"
                    )
                # 默认任务由程序填入真实比赛摘要，避免模型写出占位词或错认英雄。
                # 自定义任务保留用户指定的输出方式。
                if instructions == DEFAULT_ANALYSIS_PROMPT:
                    text = re.sub(
                        r"^```(?:text|plaintext)?\s*|\s*```$", "", text
                    ).strip()
                    result = re.fullmatch(
                        r"(?:[^\r\n]+\r?\n)?【【获胜方】】\s*【原因】[：:]\s*(.+?)\s*【关键点】[：:]\s*(.+?)\s*【【失败方】】\s*【原因】[：:]\s*(.+?)\s*【关键点】[：:]\s*(.+?)\s*【背锅】[：:]\s*(.+)",
                        text,
                        re.S,
                    )
                    if not result:
                        return self.service.err(
                            "模型未按分析格式返回内容，请重试或调整分析提示词"
                        )
                    values = [
                        re.sub(r"\s+", " ", value).strip() for value in result.groups()
                    ]
                    if not all(values):
                        return self.service.err(
                            "模型返回了空的分析项，请重试或调整分析提示词"
                        )
                    match = data["match"]
                    header = "-".join(
                        f"【{str(value or '—').strip()}】"
                        for value in (
                            match.get("played_at"),
                            match.get("mode_name"),
                            data["queried_player"]["hero_name"],
                        )
                    )
                    text = f"{header}\n【【获胜方】】\n【原因】：{values[0]}\n【关键点】：{values[1]}\n【【失败方】】\n【原因】：{values[2]}\n【关键点】：{values[3]}\n【背锅】：{values[4]}"
                return self.service.ok(text)
        except TimeoutError:
            return self.service.err("AI 对局分析超时，请稍后重试或更换响应更快的模型")
        except Exception as exc:  # noqa: BLE001 - 模型或查询失败必须给出可读提示
            logger.exception("AI 对局分析失败")
            return self.service.err(
                f"AI 对局分析失败（{type(exc).__name__}），请检查模型配置后重试"
            )
        finally:
            if task:
                self._tasks.discard(task)

    def start(
        self, keyword: str, index: int = 1, *, game_seq: str = ""
    ) -> ServiceResult:
        """启动页面分析任务，避免宿主 HTTP 请求等待整个模型生成过程。

        Args:
            keyword: 被查询的玩家。
            index: 近期对局序号。
            game_seq: 必须对应页面选中的对局。

        Returns:
            后台任务标识或无法启动的原因。
        """
        if not str(
            (self.config.get("analysis", {}) or {}).get("select_provider") or ""
        ).strip():
            return self.service.err("请先在插件配置的「AI 对局分析」中选择分析模型")
        if len(self._tasks) >= MAX_ACTIVE_ANALYSES:
            return self.service.err("当前分析任务较多，请稍后再试")
        now = time.monotonic()
        self._jobs = {
            key: value for key, value in self._jobs.items() if value["expires_at"] > now
        }
        if len(self._jobs) >= MAX_JOBS:
            oldest = min(
                (
                    key
                    for key, value in self._jobs.items()
                    if value["status"] in {"done", "error"}
                ),
                key=lambda key: self._jobs[key]["expires_at"],
                default=None,
            )
            if oldest:
                self._jobs.pop(oldest)
            else:
                return self.service.err("当前分析任务较多，请稍后再试")
        task_id = secrets.token_urlsafe(24)
        job = {
            "status": "pending",
            "message": "分析任务已启动…",
            "text": "",
            "expires_at": now + JOB_LIFETIME_SECONDS,
        }
        self._jobs[task_id] = job
        task = asyncio.create_task(self._run_job(job, keyword, index, game_seq))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return self.service.ok({"task_id": task_id, "status": "pending"})

    async def _run_job(
        self, job: dict[str, Any], keyword: str, index: int, game_seq: str
    ) -> None:
        """将共用分析结果写入页面任务状态。

        Args:
            job: 本次任务的临时状态。
            keyword: 被查询的玩家。
            index: 对局序号。
            game_seq: 已选中的对局标识。

        Returns:
            无；完成后更新状态，不保存原始对局数据。
        """
        result = await self.analyze(keyword, index, game_seq=game_seq, job=job)
        if result.get("code") == 200:
            job.update(status="done", text=result["data"], message="分析完成")
        else:
            job.update(status="error", message=result.get("msg") or "分析失败")

    def status(self, task_id: str) -> ServiceResult:
        """读取临时分析进度及结果。

        Args:
            task_id: 页面启动时返回的随机任务标识。

        Returns:
            当前状态；任务缺失或过期时返回明确错误。
        """
        job = self._jobs.get(task_id)
        if not job or job["expires_at"] <= time.monotonic():
            self._jobs.pop(task_id, None)
            return self.service.err("分析任务已过期或不存在，请重新分析")
        return self.service.ok({key: job[key] for key in ("status", "message", "text")})

    async def close(self) -> None:
        """卸载插件时取消模型调用并清理临时任务。

        Returns:
            无；等待后台任务结束，避免留下浏览器或 HTTP 之外的模型任务。
        """
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._jobs.clear()
