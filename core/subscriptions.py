"""Subscription polling and latest-only proactive message delivery."""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .models_battle import parse_battle_row
from .models_player import parse_profile
from .service import GokService
from .subscription_storage import SubscriptionStorage

KINDS = ("status", "battle")
DEFAULT_POLL_JITTER_SECONDS = 10


class SubscriptionService:
    """Poll each referenced player once and fan out only their latest event."""

    def __init__(self, service: GokService, context: Any, config: Any) -> None:
        self.service, self.context, self.config = service, context, config
        self.storage = SubscriptionStorage(service.storage.db)
        self._tasks: set[asyncio.Task] = set()
        self._wake = {kind: asyncio.Event() for kind in KINDS}
        self._locks = {kind: asyncio.Lock() for kind in KINDS}
        self._runtime = {
            kind: {
                "running": False,
                "last_poll_at": None,
                "next_poll_at": None,
                "error": "",
            }
            for kind in KINDS
        }

    def interval(self, kind: str) -> int:
        """Read a positive polling interval from the current plugin configuration.

        Args:
            kind: Subscription category.

        Returns:
            Seconds between polling rounds.
        """
        default = 60 if kind == "status" else 120
        try:
            value = int(
                (self.config.get("subscriptions", {}) or {}).get(
                    f"{kind}_poll_interval", default
                )
            )
            return value if value > 0 else default
        except (TypeError, ValueError, OverflowError):
            return default

    def jitter(self) -> int:
        """Read the shared non-negative jitter range in seconds."""
        try:
            value = int(
                (self.config.get("subscriptions", {}) or {}).get(
                    "poll_jitter", DEFAULT_POLL_JITTER_SECONDS
                )
            )
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_POLL_JITTER_SECONDS
        return max(0, value)

    def interval_bounds(self, kind: str) -> tuple[int, int]:
        """Keep every possible delay positive, even when jitter exceeds the base."""
        base, jitter = self.interval(kind), self.jitter()
        return max(1, base - jitter), base + jitter

    def next_interval(self, kind: str) -> int:
        """Draw a new delay for a round; a zero jitter preserves fixed scheduling."""
        lower, upper = self.interval_bounds(kind)
        return random.randint(lower, upper) if lower != upper else lower

    async def initialize(self) -> None:
        """Initialize storage and start independent status and battle schedulers.

        Returns:
            None.
        """
        await self.storage.initialize()
        if not self._tasks:
            for kind in KINDS:
                task = asyncio.create_task(self._loop(kind))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        """Cancel schedulers before their database and HTTP dependencies close.

        Returns:
            None.
        """
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop(self, kind: str) -> None:
        """Wait indefinitely while no session references this category.

        Args:
            kind: Subscription category.

        Returns:
            None; runs until shutdown.
        """
        state = self._runtime[kind]
        while True:
            self._wake[kind].clear()
            try:
                active = await self.storage.targets(kind, active_only=True)
                if not active:
                    state.update(running=False, next_poll_at=None, error="")
                    await self._wake[kind].wait()
                    continue
                state.update(
                    running=True, last_poll_at=time.time(), next_poll_at=None, error=""
                )
                await self.poll(kind)
            except Exception as exc:  # noqa: BLE001 - Keep other rounds alive.
                logger.exception("订阅轮询异常：%s", kind)
                state["error"] = f"轮询失败（{type(exc).__name__}）"
            state["running"] = False
            delay = self.next_interval(kind)
            state["next_poll_at"] = time.time() + delay
            try:
                await asyncio.wait_for(self._wake[kind].wait(), timeout=delay)
            except TimeoutError:
                pass

    async def poll(self, kind: str) -> None:
        """Read lightweight endpoints and compare only the newest completed data.

        Args:
            kind: Subscription category.

        Returns:
            None; snapshots and delivery outcomes are persisted.
        """
        async with self._locks[kind]:
            targets = await self.storage.targets(kind, active_only=True)
            for index, target in enumerate(targets):
                camp_id = target["camp_id"]
                if index:
                    await asyncio.sleep(0.4)
                if not await self.storage.links(kind, camp_id):
                    continue
                try:
                    profile = parse_profile(
                        await self.service.api.get_profile(camp_id), camp_id
                    )
                    if not profile.role_id:
                        raise ValueError("营地未返回有效角色")
                    snapshot = {
                        "nickname": profile.nickname,
                        "rank": f"{profile.rank_label} {profile.current_stars}星"
                        if profile.rank_label != "未知"
                        else "未知",
                    }
                    message = ""
                    latest_at = None
                    if kind == "status":
                        snapshot.update(
                            game_online=profile.game_online,
                            game_status=profile.game_status,
                        )
                        key = (
                            "offline"
                            if profile.game_online == 0
                            else "online"
                            if profile.game_online in (1, 2)
                            else None
                        )
                        if key is not None:
                            action = "离线" if key == "offline" else "上线"
                            observed_at = datetime.now(
                                ZoneInfo("Asia/Shanghai")
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            message = f"【{action}推送】\n游戏昵称：{profile.nickname}\n时间：{observed_at}\n{action}段位：{snapshot['rank']}"
                        await self.storage.observe(
                            kind,
                            camp_id,
                            snapshot,
                            key,
                            error="状态暂未返回" if key is None else "",
                        )
                    else:
                        if not await self.storage.links(kind, camp_id):
                            continue
                        result = await self.service.api.fetch_battles(
                            camp_id, max_pages=1, max_matches=20
                        )
                        matches = [
                            parse_battle_row(row, i)
                            for i, row in enumerate(result["list"])
                        ]
                        completed = [
                            match
                            for match in matches
                            if match.game_seq and match.result in {"win", "lose"}
                        ]
                        if completed:
                            match = max(
                                completed,
                                key=lambda item: (
                                    item.played_at.timestamp()
                                    if item.played_at
                                    else float("-inf")
                                ),
                            )
                            latest_at = (
                                match.played_at.timestamp() if match.played_at else None
                            )
                            if (
                                latest_at is not None
                                and target["latest_at"] is not None
                                and latest_at < target["latest_at"]
                            ):
                                continue
                            key = match.game_seq
                            snapshot["match"] = match.to_dict()
                            message = f"【战绩推送】\n{profile.nickname}-{match.mode_name}-{match.result_text}\n时间：{match.played_at_text}\n英雄：{match.hero_name}\n战绩：{match.kills}/{match.deaths}/{match.assists}\n评分：{match.score_text}"
                        elif matches:
                            # An ongoing or incomplete record cannot replace a completed cursor.
                            await self.storage.db.execute(
                                "UPDATE subscription_targets SET last_poll_at=?,error=? WHERE kind=? AND camp_id=?",
                                (time.time(), "暂未返回已完成对局", kind, camp_id),
                            )
                            continue
                        else:
                            if target["latest_key"]:
                                await self.storage.db.execute(
                                    "UPDATE subscription_targets SET last_poll_at=?,error=? WHERE kind=? AND camp_id=?",
                                    (
                                        time.time(),
                                        "未查到营地战绩，可能隐藏或暂无记录；后续继续轮询，保留上次记录",
                                        kind,
                                        camp_id,
                                    ),
                                )
                                continue
                            key = ""
                        await self.storage.observe(
                            kind,
                            camp_id,
                            snapshot,
                            key,
                            latest_at,
                            error="未查到营地战绩，可能隐藏或暂无记录；后续继续轮询"
                            if not matches
                            else "",
                        )
                    if key is not None:
                        await self._deliver(kind, camp_id, key, message)
                except Exception as exc:  # noqa: BLE001 - Isolate failed players.
                    logger.warning(
                        "订阅查询失败：%s/%s（%s）", kind, camp_id, type(exc).__name__
                    )
                    error = (
                        str(exc)
                        if isinstance(exc, ValueError)
                        else f"查询失败（{type(exc).__name__}）"
                    )
                    await self.storage.db.execute(
                        "UPDATE subscription_targets SET last_poll_at=?,error=? WHERE kind=? AND camp_id=?",
                        (time.time(), error, kind, camp_id),
                    )

    async def _deliver(self, kind: str, camp_id: str, key: str, message: str) -> None:
        """Send only the current snapshot, with no historical message queue.

        Args:
            kind: Subscription category.
            camp_id: Target player.
            key: Current normalized presence or completed battle ID.
            message: Current push text, or empty for an empty battle baseline.

        Returns:
            None; failed battle delivery retries only the next round's latest battle.
        """
        for link in await self.storage.links(kind, camp_id):
            session_id = link["session_id"]
            if link["last_key"] is None or not key:
                await self.storage.db.execute(
                    "UPDATE push_links SET last_key=? WHERE session_id=? AND kind=? AND camp_id=?",
                    (key, session_id, kind, camp_id),
                )
                continue
            if link["last_key"] == key:
                continue
            # Status failures are dropped; battle cursors advance only after delivery.
            if kind == "status":
                await self.storage.db.execute(
                    "UPDATE push_links SET last_key=? WHERE session_id=? AND kind=? AND camp_id=?",
                    (key, session_id, kind, camp_id),
                )
            try:
                sent = await asyncio.wait_for(
                    self.context.send_message(
                        session_id, MessageChain().message(message)
                    ),
                    timeout=30,
                )
                if sent is False:
                    await self.storage.db.execute(
                        "UPDATE push_sessions SET error=? WHERE session_id=?",
                        ("未找到会话对应的消息平台，请检查完整会话 ID", session_id),
                    )
                    continue
                async with self.storage.db.transaction():
                    await self.storage.db.execute(
                        "UPDATE push_links SET last_key=? WHERE session_id=? AND kind=? AND camp_id=?",
                        (key, session_id, kind, camp_id),
                    )
                    await self.storage.db.execute(
                        "UPDATE push_sessions SET last_sent_at=?,error='' WHERE session_id=?",
                        (time.time(), session_id),
                    )
            except Exception as exc:  # noqa: BLE001 - One session must not block others.
                logger.warning("会话推送失败（%s）：%s", type(exc).__name__, session_id)
                await self.storage.db.execute(
                    "UPDATE push_sessions SET error=? WHERE session_id=?",
                    (f"推送失败（{type(exc).__name__}）", session_id),
                )

    async def overview(self) -> dict[str, Any]:
        """Return page data with activity, poll times, targets and session routing.

        Returns:
            Subscription system state, safe for the plugin management page.
        """
        targets = await self.storage.targets()
        modules = {}
        for kind in KINDS:
            rows = [row for row in targets if row["kind"] == kind]
            active = sum(row["session_count"] > 0 for row in rows)
            lower, upper = self.interval_bounds(kind)
            modules[kind] = {
                **self._runtime[kind],
                "interval": self.interval(kind),
                "jitter": self.jitter(),
                "interval_min": lower,
                "interval_max": upper,
                "active_count": active,
                "targets": rows,
            }
            if not active:
                modules[kind].update(running=False, next_poll_at=None)
        return {"modules": modules, "sessions": await self.storage.sessions()}

    async def add(self, kind: str, camp_id: str) -> None:
        """Register a numeric camp ID without activating an unreferenced target.

        Args:
            kind: Subscription category.
            camp_id: Numeric camp ID.

        Returns:
            None.

        Raises:
            ValueError: Category or camp ID is invalid.
        """
        if (
            kind not in KINDS
            or not camp_id.isascii()
            or not camp_id.isdigit()
            or not 5 <= len(camp_id) <= 15
        ):
            raise ValueError("请提供订阅类型和 5~15 位数字营地 ID")
        await self.storage.add_target(kind, str(int(camp_id)))

    async def save_session(
        self, session_id: str, selections: list[tuple[str, str]]
    ) -> None:
        """Validate the host's full session ID and update routing atomically.

        Args:
            session_id: AstrBot unified message origin, including platform instance.
            selections: Status/battle camp IDs to push to this session.

        Returns:
            None.

        Raises:
            ValueError: Session ID or routing selections are invalid.
        """
        parts = session_id.split(":", 2)
        if (
            len(session_id) > 512
            or len(parts) != 3
            or not parts[0]
            or not parts[2]
            or parts[1] not in {"GroupMessage", "FriendMessage", "OtherMessage"}
            or any(ord(char) < 32 for char in session_id)
        ):
            raise ValueError(
                "请填写完整会话 ID：平台实例ID:GroupMessage/ FriendMessage:会话ID，可发送「查看订阅」获取当前会话 ID"
            )
        if any(kind not in KINDS for kind, _ in selections):
            raise ValueError("不支持的订阅类型")
        await self.storage.save_session(session_id, selections)
        for kind in KINDS:
            self._wake[kind].set()

    async def remove_target(self, kind: str, camp_id: str) -> None:
        """Remove a global target and wake the affected scheduler.

        Args:
            kind: Subscription category.
            camp_id: Target player.

        Returns:
            None.
        """
        if kind not in KINDS:
            raise ValueError("不支持的订阅类型")
        await self.storage.delete_target(kind, camp_id)
        self._wake[kind].set()

    async def remove_session(self, session_id: str) -> None:
        """Delete a session and stop targets with no remaining destinations.

        Args:
            session_id: Complete session ID.

        Returns:
            None.
        """
        await self.storage.db.execute(
            "DELETE FROM push_sessions WHERE session_id=?", (session_id,)
        )
        for kind in KINDS:
            self._wake[kind].set()

    async def subscribe(
        self, kind: str, camp_id: str, session_id: str
    ) -> dict[str, Any]:
        """Bind a chat subscription to the conversation that issued the command.

        Args:
            kind: Subscription category.
            camp_id: Resolved numeric camp ID.
            session_id: Originating conversation.

        Returns:
            Command confirmation.
        """
        await self.add(kind, camp_id)
        async with self.storage.db.transaction():
            links = await self.storage.db.fetch_all(
                "SELECT kind,camp_id FROM push_links WHERE session_id=?", (session_id,)
            )
            await self.save_session(
                session_id,
                [(row["kind"], row["camp_id"]) for row in links]
                + [(kind, str(int(camp_id)))],
            )
        label = "状态" if kind == "status" else "战绩"
        return self.service.ok(
            f"已订阅{label}：{camp_id}\n推送会话：{session_id}\n首次检查建立基准，后续只推送最新变化。"
        )

    async def list_session(self, session_id: str) -> dict[str, Any]:
        """Describe only the current chat's subscriptions and full session ID.

        Args:
            session_id: Originating conversation.

        Returns:
            Readable subscription list.
        """
        links = await self.storage.db.fetch_all(
            "SELECT kind,camp_id FROM push_links WHERE session_id=? ORDER BY kind,camp_id",
            (session_id,),
        )
        lines = [f"会话 ID：{session_id}", "当前会话订阅："]
        lines.extend(
            f"{'状态' if row['kind'] == 'status' else '战绩'}：{row['camp_id']}"
            for row in links
        )
        if not links:
            lines.append("暂无订阅")
        return self.service.ok("\n".join(lines))

    async def unsubscribe(
        self, camp_id: str, session_id: str, kind: str = ""
    ) -> dict[str, Any]:
        """Unsubscribe the current chat without altering other conversations.

        Args:
            camp_id: Target player.
            session_id: Originating conversation.
            kind: Optional status or battle filter; empty removes both.

        Returns:
            Command confirmation.
        """
        if kind not in ("", *KINDS):
            return self.service.err("取消类型请选择「状态」「战绩」或「全部」")
        await self.storage.db.execute(
            "DELETE FROM push_links WHERE session_id=? AND camp_id=? AND (?='' OR kind=?)",
            (session_id, camp_id, kind, kind),
        )
        for category in KINDS:
            self._wake[category].set()
        return self.service.ok(
            f"已取消当前会话的{'状态' if kind == 'status' else '战绩' if kind == 'battle' else '全部'}订阅：{camp_id}"
        )
