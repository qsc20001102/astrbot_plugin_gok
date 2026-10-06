"""本地数据仓库：仅保存营地 ID、游戏角色名与管理页显示名称的映射。

这里**不做任何数据缓存** —— 玩家概况与对局记录每次都实时向营地接口请求，
不落库、不聚合、不增量同步。营地侧数据变化后立即反映到查询结果。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .sqlite import AsyncSQLiteDB

logger = logging.getLogger(__name__)

__all__ = ["GokStorage"]

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS aliases (
        gokid      INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,
        role_name  TEXT NOT NULL DEFAULT '',
        manually_named INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_aliases_name ON aliases(name)",
)

# 早期版本曾把玩家概况与对局写进本地库作为缓存；既然不再缓存数据，
# 这两张表已无用途，初始化时清理掉（里面只有可重新拉取的缓存数据）。
_OBSOLETE_TABLES = ("matches", "players")


class GokStorage:
    """插件本地数据访问层（仅角色别名）。"""

    def __init__(self, db: AsyncSQLiteDB) -> None:
        self.db = db

    # ------------------------------------------------------------------ 建表
    async def initialize(self) -> None:
        for statement in _SCHEMA:
            await self.db.execute(statement)
        columns = {
            row["name"] for row in await self.db.fetch_all("PRAGMA table_info(aliases)")
        }
        if "role_name" not in columns:
            await self.db.execute(
                "ALTER TABLE aliases ADD COLUMN role_name TEXT NOT NULL DEFAULT ''"
            )
        if "manually_named" not in columns:
            await self.db.execute(
                "ALTER TABLE aliases ADD COLUMN manually_named INTEGER NOT NULL DEFAULT 0"
            )
            await self.db.execute("UPDATE aliases SET manually_named=1")
        await self._drop_obsolete_cache_tables()
        logger.debug("本地数据表已就绪（仅角色别名）")

    async def _drop_obsolete_cache_tables(self) -> None:
        for table in _OBSOLETE_TABLES:
            exists = await self.db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if exists:
                logger.info("清理旧版缓存表：%s", table)
                await self.db.execute(f"DROP TABLE IF EXISTS {table}")

    # ------------------------------------------------------------------ 别名
    async def add_alias(self, gokid: int, name: str) -> bool:
        """新增别名；已存在同 gokid 时返回 False。"""
        existing = await self.db.fetch_one(
            "SELECT gokid FROM aliases WHERE gokid=?", (gokid,)
        )
        if existing:
            return False
        now = time.time()
        await self.db.execute(
            "INSERT INTO aliases (gokid, name, created_at, updated_at, manually_named) VALUES (?,?,?,?,1)",
            (gokid, name, now, now),
        )
        return True

    async def update_alias(self, gokid: int, name: str) -> bool:
        existing = await self.db.fetch_one(
            "SELECT gokid FROM aliases WHERE gokid=?", (gokid,)
        )
        if not existing:
            return False
        await self.db.execute(
            "UPDATE aliases SET name=?, updated_at=?, manually_named=1 WHERE gokid=?",
            (name, time.time(), gokid),
        )
        return True

    async def remember_player(self, gokid: int, role_name: str) -> None:
        """Record the queried role name while preserving administrator edits.

        Args:
            gokid: Successfully queried Camp ID.
            role_name: Game role name returned by Camp.
        """
        now = time.time()
        await self.db.execute(
            "INSERT INTO aliases (gokid,name,role_name,created_at,updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(gokid) DO UPDATE SET role_name=excluded.role_name, "
            "name=CASE WHEN aliases.manually_named=1 THEN aliases.name ELSE excluded.name END, "
            "updated_at=excluded.updated_at",
            (gokid, role_name, role_name, now, now),
        )

    async def delete_alias(self, gokid: int) -> bool:
        existing = await self.db.fetch_one(
            "SELECT gokid FROM aliases WHERE gokid=?", (gokid,)
        )
        if not existing:
            return False
        await self.db.execute("DELETE FROM aliases WHERE gokid=?", (gokid,))
        return True

    async def list_aliases(self) -> list[dict[str, Any]]:
        return await self.db.fetch_all(
            "SELECT gokid, name, role_name, manually_named, created_at, updated_at FROM aliases ORDER BY updated_at DESC"
        )

    async def find_aliases(self, keyword: str) -> list[dict[str, Any]]:
        """按别名或营地 ID 模糊查询。"""
        pattern = f"%{keyword}%"
        return await self.db.fetch_all(
            "SELECT gokid, name, role_name, manually_named FROM aliases WHERE name LIKE ? OR role_name LIKE ? OR CAST(gokid AS TEXT) LIKE ?"
            " ORDER BY updated_at DESC",
            (pattern, pattern, pattern),
        )

    async def resolve_gokid(self, keyword: str) -> int | None:
        """把用户输入解析成营地 ID：纯数字直接当 ID，否则查别名。"""
        text = (keyword or "").strip()
        if not text:
            return None
        if text.isdigit() and 5 <= len(text) <= 15:
            return int(text)
        rows = await self.db.fetch_all(
            "SELECT gokid FROM aliases WHERE name=? OR role_name=?",
            (text, text),
        )
        if rows:
            return int(rows[0]["gokid"]) if len(rows) == 1 else None
        matches = await self.find_aliases(text)
        return int(matches[0]["gokid"]) if len(matches) == 1 else None

    async def count_aliases(self) -> int:
        value = await self.db.fetch_value("SELECT COUNT(*) FROM aliases", default=0)
        return int(value or 0)
