"""营地数据接口封装：玩家资料、战绩列表（翻页）、赛季页、对局详情。

对应参考实现的 `src/lib/camp/camp-api.ts`。营地接口不返回总页数，
只能靠 `hasMore` + `lastTime` 逐页拉取，因此这里统一封在一个带节流与
去重的翻页函数里（默认间隔 400ms，避免触发频控）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .camp_client import CampClient

__all__ = [
    "CampDataApi",
    "BATTLE_PAGE_DELAY_SECONDS",
    "BATTLE_QUERY_MAX_PAGES",
    "BATTLE_QUERY_MAX_MATCHES",
]

BATTLE_PAGE_DELAY_SECONDS = 0.4
BATTLE_QUERY_MAX_PAGES = 8
BATTLE_QUERY_MAX_MATCHES = 100


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    """营地响应外层通常是 `{returnCode, data: {...}}`，这里统一取内层。"""
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else payload


class CampDataApi:
    """营地业务接口。"""

    def __init__(self, client: CampClient) -> None:
        self.client = client

    # ------------------------------------------------------------------ 玩家资料
    async def get_profile(self, camp_id: str) -> dict[str, Any]:
        """查询玩家资料（含段位、角色列表、头像）。"""
        return await self.client.request(
            "/game/koh/profile",
            {
                "targetUserId": camp_id,
                "targetRoleId": "0",
                "resVersion": "3",
                "recommendPrivacy": "0",
                "apiVersion": "2",
            },
        )

    async def get_season_page(self, role_id: str) -> dict[str, Any]:
        """查询本赛季页（赛季场次、胜场、金牌数、巅峰分等）。"""
        return await self.client.request(
            "/game/seasonpage",
            {"recommendPrivacy": 0, "seasonId": 0, "roleId": role_id},
        )

    # ------------------------------------------------------------------ 战绩列表
    async def get_battle_list(
        self, camp_id: str, last_time: int | str = 0
    ) -> dict[str, Any]:
        """拉取一页战绩。`lastTime` 传上一页返回的游标。"""
        return await self.client.request(
            "/game/morebattlelist",
            {
                "lastTime": last_time,
                "recommendPrivacy": 0,
                "apiVersion": 5,
                "friendUserId": camp_id,
                "option": 0,
            },
        )

    async def fetch_battles(
        self,
        camp_id: str,
        *,
        max_pages: int = BATTLE_QUERY_MAX_PAGES,
        max_matches: int = BATTLE_QUERY_MAX_MATCHES,
        page_delay: float = BATTLE_PAGE_DELAY_SECONDS,
    ) -> dict[str, Any]:
        """Fetch recent matches directly from Camp, following its page cursor.

        Args:
            camp_id: Camp ID to query.
            max_pages: Maximum number of pages to request.
            max_matches: Maximum number of matches to return.
            page_delay: Delay between pages in seconds.

        Returns:
            Match list, number of fetched pages, and whether more pages exist.
        """

        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        last_time: int | str = 0
        pages = 0
        has_more = True

        while has_more and pages < max(1, max_pages):
            if pages > 0 and page_delay > 0:
                await asyncio.sleep(page_delay)

            payload = await self.get_battle_list(camp_id, last_time)
            data = _unwrap(payload)
            page_items = _as_list(data.get("list")) or _as_list(data.get("battle_list"))

            for row in page_items:
                row_id = str(
                    row.get("gameSeq")
                    or row.get("battleId")
                    or row.get("battle_id")
                    or ""
                )
                key = row_id or "-".join(
                    str(row.get(k) or "")
                    for k in (
                        "dtEventTime",
                        "heroId",
                        "killcnt",
                        "deadcnt",
                        "assistcnt",
                    )
                )
                if key in seen:
                    continue
                seen.add(key)
                collected.append(row)
                if len(collected) >= max_matches:
                    break

            pages += 1
            has_more = bool(data.get("hasMore"))
            if len(collected) >= max_matches:
                break

            next_cursor = data.get("lastTime")
            if next_cursor in (None, "", last_time):
                has_more = False
            else:
                last_time = next_cursor

        return {
            "list": collected,
            "pages": pages,
            "has_more": has_more,
        }

    # ------------------------------------------------------------------ 对局详情
    async def get_battle_detail(
        self,
        *,
        game_seq: str,
        game_svr: str,
        relay_svr: str,
        battle_type: int,
        target_role_id: str,
    ) -> dict[str, Any]:
        """查询单场对局详情（十人面板、出装、经济、输出等）。"""
        return await self.client.request(
            "/game/battledetail",
            {
                "recommendPrivacy": 0,
                "battleType": battle_type,
                "gameSvr": game_svr,
                "relaySvr": relay_svr,
                "targetRoleId": target_role_id,
                "gameSeq": game_seq,
            },
        )
