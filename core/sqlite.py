"""异步 SQLite 封装：单连接 + 任务可重入串行锁 + 嵌套事务。

同一插件的多个协程会共用一条连接，aiosqlite 的连接本身不是并发安全的，
因此这里用「锁 + 同任务可重入」的方式保证串行；多步写入走 `transaction()`
以获得原子性与异常回滚。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

__all__ = ["AsyncSQLiteDB"]


class AsyncSQLiteDB:
    """轻量异步 SQLite 封装。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0

    # ------------------------------------------------------------------ 生命周期
    async def connect(self) -> None:
        async with self._serialized():
            if self.conn is None:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                self.conn = await aiosqlite.connect(self.db_path)
                self.conn.row_factory = aiosqlite.Row
                await self.conn.execute("PRAGMA journal_mode=WAL")
                await self.conn.execute("PRAGMA foreign_keys=ON")
                await self.conn.commit()

    async def close(self) -> None:
        async with self._serialized():
            if self.conn is not None:
                await self.conn.close()
                self.conn = None

    @property
    def connected(self) -> bool:
        return self.conn is not None

    # ------------------------------------------------------------------ 串行/事务
    @asynccontextmanager
    async def _serialized(self) -> AsyncIterator[None]:
        """同任务可重入的串行区；跨任务互斥。"""
        task = asyncio.current_task()
        if self._owner is task:
            yield
            return
        async with self._lock:
            self._owner = task
            try:
                yield
            finally:
                self._owner = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """事务上下文；嵌套时自动使用 SAVEPOINT。"""
        if self.conn is None:
            raise RuntimeError("数据库尚未连接")
        async with self._serialized():
            nested = self._depth > 0
            savepoint = f"gok_sp_{self._depth}"
            self._depth += 1
            try:
                if nested:
                    await self.conn.execute(f"SAVEPOINT {savepoint}")
                else:
                    await self.conn.execute("BEGIN IMMEDIATE")
                yield
                if nested:
                    await self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                else:
                    await self.conn.commit()
            except BaseException:
                try:
                    if nested:
                        await self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        await self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                    else:
                        await self.conn.rollback()
                except Exception:  # noqa: BLE001 - 回滚失败不应掩盖原始异常
                    logger.exception("事务回滚失败")
                raise
            finally:
                self._depth -= 1

    # ------------------------------------------------------------------ 执行
    async def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        async with self.transaction():
            await self._require_conn().execute(sql, tuple(params))

    async def execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        data = [tuple(row) for row in rows]
        if not data:
            return
        async with self.transaction():
            await self._require_conn().executemany(sql, data)

    async def execute_insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        async with self.transaction():
            cursor = await self._require_conn().execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)

    async def fetch_one(
        self, sql: str, params: Sequence[Any] = ()
    ) -> dict[str, Any] | None:
        async with self._serialized():
            cursor = await self._require_conn().execute(sql, tuple(params))
            async with cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        async with self._serialized():
            cursor = await self._require_conn().execute(sql, tuple(params))
            async with cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_value(
        self, sql: str, params: Sequence[Any] = (), default: Any = None
    ) -> Any:
        row = await self.fetch_one(sql, params)
        if not row:
            return default
        return next(iter(row.values()), default)

    def _require_conn(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("数据库尚未连接，请先调用 connect()")
        return self.conn
