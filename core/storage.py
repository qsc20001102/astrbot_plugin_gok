"""本地数据仓库：仅保存营地 ID、真实游戏昵称与独立人工别名的映射。

这里**不做任何数据缓存** —— 玩家概况与对局记录每次都实时向营地接口请求，
不落库、不聚合、不增量同步。营地侧数据变化后立即反映到查询结果。
"""

from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger

from .sqlite import AsyncSQLiteDB

__all__ = ["GokStorage"]

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS aliases (
        gokid      INTEGER PRIMARY KEY,
        role_name  TEXT NOT NULL DEFAULT '',
        alias      TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
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
        async with self.db.transaction():
            columns = {
                row["name"]
                for row in await self.db.fetch_all("PRAGMA table_info(aliases)")
            }
            if columns and "alias" not in columns:
                # 保留人工别名；尚未验证的历史游戏昵称保持为空。
                role_column = "role_name" if "role_name" in columns else "''"
                alias_column = (
                    "CASE WHEN manually_named=1 THEN name ELSE '' END"
                    if "manually_named" in columns
                    else "name"
                )
                await self.db.execute(
                    _SCHEMA[0].replace("IF NOT EXISTS aliases", "aliases_v3")
                )
                await self.db.execute(
                    "INSERT INTO aliases_v3 (gokid,role_name,alias,created_at,updated_at) "
                    f"SELECT gokid,{role_column},{alias_column},created_at,updated_at FROM aliases"
                )
                await self.db.execute("DROP TABLE aliases")
                await self.db.execute("ALTER TABLE aliases_v3 RENAME TO aliases")
            else:
                await self.db.execute(_SCHEMA[0])
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias)"
            )
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_aliases_role_name ON aliases(role_name)"
            )
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
            "INSERT INTO aliases (gokid, role_name, created_at, updated_at) VALUES (?,?,?,?)",
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
            "UPDATE aliases SET alias=?, updated_at=? WHERE gokid=?",
            (name, time.time(), gokid),
        )
        return True

    async def remember_player(self, gokid: int, role_name: str) -> None:
        """保存接口确认的游戏昵称，不覆盖管理员设置的别名。

        Args:
            gokid: 目标营地 ID。
            role_name: 接口返回的真实游戏昵称。

        Returns:
            真实昵称有效并完成保存时为真。
        """
        now = time.time()
        await self.db.execute(
            "INSERT INTO aliases (gokid,role_name,created_at,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(gokid) DO UPDATE SET role_name=excluded.role_name, "
            "updated_at=excluded.updated_at",
            (gokid, role_name, now, now),
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
            "SELECT gokid, role_name, alias, created_at, updated_at FROM aliases ORDER BY updated_at DESC"
        )

    async def find_aliases(
        self, keyword: str, *, exact: bool = False
    ) -> list[dict[str, Any]]:
        """按别名或营地 ID 模糊查询。"""
        if exact:
            rows = await self.db.fetch_all(
                "SELECT gokid,role_name,alias FROM aliases WHERE alias=? AND alias<>'' ORDER BY updated_at DESC",
                (keyword,),
            )
            return rows or await self.db.fetch_all(
                "SELECT gokid,role_name,alias FROM aliases WHERE role_name=? ORDER BY updated_at DESC",
                (keyword,),
            )
        pattern = f"%{keyword}%"
        return await self.db.fetch_all(
            "SELECT gokid, role_name, alias FROM aliases WHERE alias LIKE ? OR role_name LIKE ? OR CAST(gokid AS TEXT) LIKE ?"
            " ORDER BY updated_at DESC",
            (pattern, pattern, pattern),
        )

    async def resolve_gokid(self, keyword: str) -> int | None:
        """把用户输入解析成营地 ID：纯数字直接当 ID，否则查别名。"""
        text = (keyword or "").strip()
        if not text:
            return None
        if text.isascii() and text.isdigit() and 5 <= len(text) <= 15:
            return int(text)
        rows = await self.find_aliases(text, exact=True)
        return int(rows[0]["gokid"]) if len(rows) == 1 else None

    async def count_aliases(self) -> int:
        value = await self.db.fetch_value("SELECT COUNT(*) FROM aliases", default=0)
        return int(value or 0)
