"""Persistent subscription targets, session routing and delivery cursors."""

from __future__ import annotations

import json
import time
from typing import Any

from .sqlite import AsyncSQLiteDB


class SubscriptionStorage:
    """Keep one latest snapshot per target and independent cursors per session."""

    def __init__(self, db: AsyncSQLiteDB) -> None:
        self.db = db

    async def initialize(self) -> None:
        """Create subscription tables in the existing plugin database.

        Returns:
            None.
        """
        async with self.db.transaction():
            for sql in (
                "CREATE TABLE IF NOT EXISTS subscription_targets ("
                "kind TEXT NOT NULL, camp_id TEXT NOT NULL, nickname TEXT NOT NULL DEFAULT '', "
                "snapshot TEXT NOT NULL DEFAULT '{}', latest_key TEXT, latest_at REAL, "
                "last_poll_at REAL, error TEXT NOT NULL DEFAULT '', PRIMARY KEY(kind,camp_id))",
                "CREATE TABLE IF NOT EXISTS push_sessions (session_id TEXT PRIMARY KEY, "
                "last_sent_at REAL, error TEXT NOT NULL DEFAULT '')",
                "CREATE TABLE IF NOT EXISTS push_links (session_id TEXT NOT NULL, kind TEXT NOT NULL, "
                "camp_id TEXT NOT NULL, last_key TEXT, PRIMARY KEY(session_id,kind,camp_id), "
                "FOREIGN KEY(session_id) REFERENCES push_sessions(session_id) ON DELETE CASCADE, "
                "FOREIGN KEY(kind,camp_id) REFERENCES subscription_targets(kind,camp_id) ON DELETE CASCADE)",
                "CREATE INDEX IF NOT EXISTS idx_push_links_target ON push_links(kind,camp_id)",
            ):
                await self.db.execute(sql)

    async def targets(
        self, kind: str = "", *, active_only: bool = False
    ) -> list[dict[str, Any]]:
        """List targets and count the sessions that keep each poller active.

        Args:
            kind: Optional status or battle filter.
            active_only: Include only targets linked to at least one session.

        Returns:
            Targets with parsed latest snapshots and session counts.
        """
        rows = await self.db.fetch_all(
            "SELECT t.*,COUNT(l.session_id) AS session_count FROM subscription_targets t "
            "LEFT JOIN push_links l ON l.kind=t.kind AND l.camp_id=t.camp_id "
            "WHERE (?='' OR t.kind=?) GROUP BY t.kind,t.camp_id "
            + ("HAVING COUNT(l.session_id)>0 " if active_only else "")
            + "ORDER BY t.camp_id",
            (kind, kind),
        )
        for row in rows:
            row["snapshot"] = json.loads(row["snapshot"])
        return rows

    async def add_target(self, kind: str, camp_id: str, nickname: str = "") -> None:
        """Add a target without querying the upstream service.

        Args:
            kind: Subscription category.
            camp_id: Valid camp ID.
            nickname: Previously resolved player nickname, if available.

        Returns:
            None; an existing subscription is preserved.
        """
        await self.db.execute(
            "INSERT INTO subscription_targets(kind,camp_id,nickname) VALUES (?,?,?) "
            "ON CONFLICT(kind,camp_id) DO NOTHING",
            (kind, camp_id, nickname),
        )

    async def delete_target(self, kind: str, camp_id: str) -> None:
        """Remove a target and all session mappings through cascading deletion.

        Args:
            kind: Subscription category.
            camp_id: Camp ID to remove.

        Returns:
            None.
        """
        await self.db.execute(
            "DELETE FROM subscription_targets WHERE kind=? AND camp_id=?",
            (kind, camp_id),
        )

    async def save_session(
        self, session_id: str, selections: list[tuple[str, str]]
    ) -> None:
        """Replace routing selections while preserving unchanged delivery cursors.

        Args:
            session_id: Complete AstrBot unified message origin.
            selections: Selected category/camp ID pairs, all of which must exist.

        Returns:
            None.

        Raises:
            ValueError: A selected target no longer exists.
        """
        async with self.db.transaction():
            for kind, camp_id in selections:
                if not await self.db.fetch_one(
                    "SELECT 1 FROM subscription_targets WHERE kind=? AND camp_id=?",
                    (kind, camp_id),
                ):
                    raise ValueError("所选订阅已不存在，请刷新页面后再试")
            await self.db.execute(
                "INSERT INTO push_sessions(session_id) VALUES (?) ON CONFLICT DO NOTHING",
                (session_id,),
            )
            existing = await self.db.fetch_all(
                "SELECT kind,camp_id FROM push_links WHERE session_id=?", (session_id,)
            )
            chosen = set(selections)
            for row in existing:
                if (row["kind"], row["camp_id"]) not in chosen:
                    await self.db.execute(
                        "DELETE FROM push_links WHERE session_id=? AND kind=? AND camp_id=?",
                        (session_id, row["kind"], row["camp_id"]),
                    )
            await self.db.execute_many(
                "INSERT INTO push_links(session_id,kind,camp_id) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                ((session_id, kind, camp_id) for kind, camp_id in chosen),
            )

    async def sessions(self) -> list[dict[str, Any]]:
        """List sessions with their selected status and battle targets.

        Returns:
            Session rows containing a list of subscription mappings.
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM push_sessions ORDER BY session_id"
        )
        links = await self.db.fetch_all(
            "SELECT session_id,kind,camp_id FROM push_links ORDER BY kind,camp_id"
        )
        for row in rows:
            row["subscriptions"] = [
                link for link in links if link["session_id"] == row["session_id"]
            ]
        return rows

    async def links(self, kind: str, camp_id: str) -> list[dict[str, Any]]:
        """Read the current routing and per-session cursor for a target.

        Args:
            kind: Subscription category.
            camp_id: Target player.

        Returns:
            Current session mappings.
        """
        return await self.db.fetch_all(
            "SELECT * FROM push_links WHERE kind=? AND camp_id=?", (kind, camp_id)
        )

    async def observe(
        self,
        kind: str,
        camp_id: str,
        snapshot: dict[str, Any],
        key: str | None,
        latest_at: float | None = None,
        error: str = "",
    ) -> None:
        """Store the latest observed data, never a backlog of historical events.

        Args:
            kind: Subscription category.
            camp_id: Target player.
            snapshot: Latest public display data.
            key: Valid comparison key; None preserves the previous known key.
            latest_at: Latest completed battle time, if available.
            error: Readable polling outcome.

        Returns:
            None.
        """
        await self.db.execute(
            "UPDATE subscription_targets SET nickname=?,snapshot=?,latest_key=COALESCE(?,latest_key), "
            "latest_at=COALESCE(?,latest_at),last_poll_at=?,error=? WHERE kind=? AND camp_id=?",
            (
                snapshot.get("nickname", ""),
                json.dumps(snapshot, ensure_ascii=False, allow_nan=False),
                key,
                latest_at,
                time.time(),
                error,
                kind,
                camp_id,
            ),
        )
