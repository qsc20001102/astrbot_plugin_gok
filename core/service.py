"""业务编排层：把营地接口结果整理成插件需要的查询结果。

统一返回契约（与原插件保持一致，消息层只认这一种）：

    {"code": 200|400, "msg": "错误说明", "data": {...}, "temp": "模板名"}

**不做任何数据缓存**：每次查询都实时请求营地接口，营地侧数据变化后立即生效。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .camp_api import CampDataApi
from .camp_auth import CampAuthStore
from .camp_client import CampApiError
from .camp_login import CampLoginManager
from .heroes import hero_repository
from .models import (
    MatchRecord,
    PlayerProfile,
    SeasonStats,
    build_battle_comment,
    collect_image_resources,
    parse_battle_row,
    parse_profile,
    parse_season_stats,
)
from .storage import GokStorage

__all__ = ["GokService", "ServiceResult"]

ServiceResult = dict[str, Any]

# 营地错误码 → 给用户看的中文提示
_ERROR_HINTS: dict[str, str] = {
    "auth": "营地登录态已失效，请到插件页面重新扫码登录",
    "hidden": "该召唤师隐藏了个人战绩，请在王者营地开放战绩后重试",
    "rate_limit": "操作过于频繁，请稍后再试",
    "not_found": "未找到该营地 ID 对应的游戏角色",
    "upstream": "营地接口暂时不可用，请稍后再试",
}

# 单次查询最多向营地拉取的对局数（用于本地筛选与详情定位）
MAX_MATCHES_PER_QUERY = 50


class GokService:
    """插件业务逻辑。"""

    def __init__(
        self,
        config: Any,
        storage: GokStorage,
        auth_store: CampAuthStore,
        api: CampDataApi,
        login_manager: CampLoginManager,
    ) -> None:
        self.config = config
        self.storage = storage
        self.auth_store = auth_store
        self.api = api
        self.login = login_manager

    # ------------------------------------------------------------------ 返回构造
    @staticmethod
    def ok(data: Any = None, temp: str = "") -> ServiceResult:
        return {
            "code": 200,
            "msg": "",
            "data": data if data is not None else {},
            "temp": temp,
        }

    @staticmethod
    def err(message: str) -> ServiceResult:
        return {"code": 400, "msg": message, "data": {}, "temp": ""}

    @staticmethod
    def error_message(exc: CampApiError) -> str:
        if exc.code in {"auth", "upstream"} and str(exc):
            return str(exc)
        hint = _ERROR_HINTS.get(exc.code)
        if hint:
            return hint
        return str(exc)

    # ------------------------------------------------------------------ 输入解析
    async def resolve_camp_id(self, keyword: str) -> int | None:
        """把用户输入（营地 ID 或别名）解析成营地 ID。"""
        return await self.storage.resolve_gokid((keyword or "").strip())

    async def require_camp_id(
        self, keyword: str
    ) -> tuple[int | None, ServiceResult | None]:
        """解析营地 ID；失败时直接返回可用的错误结果。"""
        text = (keyword or "").strip()
        if not text:
            return None, self.err("请提供营地 ID 或已保存的角色别名")
        if text.isdigit():
            if not text.isascii() or not 5 <= len(text) <= 15:
                return None, self.err("营地 ID 应为 5~15 位数字")
            return int(text), None
        rows = await self.storage.find_aliases(text, exact=True)
        if rows:
            candidates = [
                {
                    "uid": str(row["gokid"]),
                    "name": row["role_name"] or row["alias"],
                    "alias": row["alias"],
                    "region": "",
                    "dw": "",
                }
                for row in rows
            ]
        else:
            try:
                candidates = await self.api.search_users(text)
            except CampApiError as exc:
                return None, self.err(self.error_message(exc))
        if not candidates:
            return None, self.err(
                f"没有搜索到「{text}」对应的营地用户，请检查昵称或使用营地 ID"
            )
        if len(candidates) == 1:
            return int(candidates[0]["uid"]), None
        result = self.err(f"「{text}」匹配多个角色，请选择要查询的用户")
        result["data"] = {"candidates": candidates}
        return None, result

    # ------------------------------------------------------------------ 数据获取
    async def _load_profile(
        self, camp_id: str
    ) -> tuple[PlayerProfile | None, SeasonStats | None, ServiceResult | None]:
        """实时拉取玩家概况与赛季统计（无缓存）。"""
        try:
            payload = await self.api.get_profile(camp_id)
        except CampApiError as exc:
            return None, None, self.err(self.error_message(exc))

        profile = parse_profile(payload, camp_id)
        if not profile.role_id:
            return (
                None,
                None,
                self.err(f"未找到营地 ID {camp_id} 对应的游戏角色，请确认 ID 是否正确"),
            )

        season: SeasonStats | None = None
        try:
            season_payload = await self.api.get_season_page(profile.role_id)
            season = parse_season_stats(season_payload)
        except CampApiError as exc:
            # 赛季页失败不阻断主流程
            logger.info("赛季页获取失败(%s)，跳过赛季统计", exc.code)

        if season is not None:
            _apply_season(profile, season)
        return profile, season, None

    async def _load_matches(
        self, camp_id: str, *, max_matches: int = MAX_MATCHES_PER_QUERY, option: int = 0
    ) -> tuple[list[MatchRecord], ServiceResult | None]:
        """实时拉取战绩列表（无缓存、不做增量）。"""
        try:
            result = await self.api.fetch_battles(
                camp_id, max_matches=max(1, max_matches), option=option
            )
        except CampApiError as exc:
            return [], self.err(self.error_message(exc))
        rows = result["list"]
        return [parse_battle_row(row, i) for i, row in enumerate(rows)], None

    # ------------------------------------------------------------------ 查询功能
    async def player_overview(self, keyword: str) -> ServiceResult:
        """「资料」：玩家概况 + 本赛季常用英雄。"""
        camp_id, error = await self.require_camp_id(keyword)
        if error:
            return error
        assert camp_id is not None

        profile, season, error = await self._load_profile(str(camp_id))
        if error:
            return error
        assert profile is not None

        data = {
            "profile": profile.to_dict(),
            # 本赛季英雄统计直接来自营地赛季页，不是本地聚合
            "season_heroes": season.heroes if season else [],
            "season_name": season.season_name if season else "",
            "hide_match": profile.hide_match,
        }
        await self._remember_player(profile)
        return self.ok(data, temp="profile.html")

    async def battle_report(
        self, keyword: str, limit: int = 10, *, option: int = 0
    ) -> ServiceResult:
        """「战绩」：最近对局列表 + 汇总 + 锐评数据。"""
        if option not in (0, 1, 4):
            return self.err("不支持的战绩类型")
        camp_id, error = await self.require_camp_id(keyword)
        if error:
            return error
        assert camp_id is not None

        profile, _, error = await self._load_profile(str(camp_id))
        if error:
            return error
        assert profile is not None

        matches, error = await self._load_matches(
            str(camp_id), max_matches=max(limit, MAX_MATCHES_PER_QUERY), option=option
        )
        if error:
            return error
        if option:
            mode = {1: "ranked", 4: "peak"}[option]
            matches = [match for match in matches if match.mode == mode]
        if not matches:
            # 营地对隐藏战绩不返回错误码，而是在角色资料里给出 hideMatch=1
            if profile.hide_match:
                return self.err(
                    f"{profile.nickname} 已在王者营地隐藏了战绩，无法查询。\n"
                    "需要对方在营地 → 设置 → 隐私中开放战绩后才可查询。"
                )
            return self.err(
                f"没有查到 {profile.nickname} 的对局记录，"
                "可能是近期没有参与对局，或战绩仅自己可见。"
            )

        shown = matches[: max(1, limit)]
        total = len(matches)
        wins = sum(1 for m in matches if m.win)
        avg_kda = round(sum(m.kda for m in matches) / total, 1)
        scored = [m.score for m in matches if m.score]
        avg_score = round(sum(scored) / len(scored), 1) if scored else 0.0

        data = {
            "profile": profile.to_dict(),
            "list": [m.to_dict() for m in shown],
            "option": option,
            "query_title": {0: "全部战绩", 1: "排位战绩", 4: "巅峰战绩"}[option],
            "summary": {
                "total": total,
                "wins": wins,
                "loses": total - wins,
                "win_rate": round(wins / total * 100, 1),
                "avg_kda": avg_kda,
                "avg_score": avg_score,
                "mvp_count": sum(1 for m in matches if m.mvp_type == "mvp"),
                "svp_count": sum(1 for m in matches if m.mvp_type == "svp"),
                "gold_count": sum(1 for m in matches if m.gold),
            },
            "comment": build_battle_comment(shown, limit=len(shown)),
        }
        await self._remember_player(profile)
        return self.ok(data, temp="battle.html")

    async def battle_detail(
        self, keyword: str, index: int = 1, *, game_seq: str = ""
    ) -> ServiceResult:
        """「对局详情」：按序号查看一场对局的十人面板。"""
        camp_id, error = await self.require_camp_id(keyword)
        if error:
            return error
        assert camp_id is not None

        profile, _, error = await self._load_profile(str(camp_id))
        if error:
            return error
        assert profile is not None

        matches, error = await self._load_matches(str(camp_id))
        if error:
            return error
        if not matches:
            if profile.hide_match:
                return self.err(
                    f"{profile.nickname} 已在王者营地隐藏了战绩，无法查询对局详情。"
                )
            return self.err(f"没有查到 {profile.nickname} 的对局记录")

        position = max(1, int(index))
        if game_seq:
            position = next(
                (i + 1 for i, row in enumerate(matches) if row.game_seq == game_seq), 0
            )
            if not position:
                return self.err("该对局已不在近期战绩列表中，请重新查询战绩")
        if position > len(matches):
            return self.err(f"序号超出范围，当前可查询 {len(matches)} 场对局")

        match = matches[position - 1]
        if not (match.game_seq and match.game_svr and match.relay_svr):
            return self.err("该对局缺少详情参数，营地未返回对局标识")
        if not match.battle_type:
            return self.err("该对局类型不支持详情查询")

        try:
            payload = await self.api.get_battle_detail(
                game_seq=match.game_seq,
                game_svr=match.game_svr,
                relay_svr=match.relay_svr,
                battle_type=match.battle_type,
                target_role_id=profile.role_id,
            )
        except CampApiError as exc:
            return self.err(self.error_message(exc))

        data = _parse_battle_detail(payload, profile.role_id)
        data["match"] = match.to_dict(detailed=True)
        data["profile"] = profile.to_dict()
        data["index"] = position
        data["total"] = len(matches)
        await self._remember_player(profile)
        return self.ok(data, temp="detail.html")

    async def _remember_player(self, profile: PlayerProfile) -> None:
        """Persist real nicknames after successful queries through either input path.

        Args:
            profile: Successfully retrieved player profile.
        """
        if profile.nickname not in {
            "",
            "未知",
            f"营地{profile.camp_id}",
        }:
            await self.storage.remember_player(int(profile.camp_id), profile.nickname)

    # ------------------------------------------------------------------ 别名管理
    async def update_alias(self, gokid: int, name: str) -> ServiceResult:
        name = (name or "").strip()
        if len(name) > 80:
            return self.err("别名最多 80 个字符")
        if not await self.storage.update_alias(int(gokid), name):
            return self.err(f"没有找到营地 ID：{gokid}")
        return self.ok(f"角色别名已更新\n营地 ID：{gokid}\n别名：{name or '未设置'}")

    async def delete_alias(self, gokid: int) -> ServiceResult:
        if not await self.storage.delete_alias(int(gokid)):
            return self.err(f"没有找到营地 ID：{gokid}")
        return self.ok(f"角色删除成功\n营地 ID：{gokid}")

    async def list_aliases(self) -> ServiceResult:
        aliases = await self.storage.list_aliases()
        if not aliases:
            return self.err("还没有保存角色，请先使用营地 ID 或昵称查询资料、战绩")
        return self.ok({"list": aliases}, temp="aliases.html")

    async def search_aliases(self, keyword: str) -> ServiceResult:
        text = (keyword or "").strip()
        if not text:
            return self.err("请提供要查询的别名或营地 ID")
        matches = await self.storage.find_aliases(text)
        if not matches:
            return self.err(f"没有匹配「{text}」的角色")
        return self.ok({"list": matches, "keyword": text}, temp="aliases.html")

    # ------------------------------------------------------------------ 账号/统计
    async def account_summary(self) -> dict[str, Any]:
        return await self.auth_store.summary()

    async def local_stats(self) -> dict[str, Any]:
        """本地只保存角色别名，没有数据缓存。"""
        return {"aliases": await self.storage.count_aliases()}

    async def close(self) -> None:
        """预留：上层统一关闭 HTTP 会话。"""


# ---------------------------------------------------------------------- 辅助
def _apply_season(profile: PlayerProfile, season: SeasonStats) -> None:
    """把赛季页统计回填到玩家概况（仅覆盖赛季页确实给出的字段）。"""
    if season.season_games is not None:
        profile.season_games = season.season_games
    if season.season_wins is not None:
        profile.season_wins = season.season_wins
    if season.gold_count is not None:
        profile.gold_count = season.gold_count
    if season.rank_score is not None:
        profile.rank_score = season.rank_score
    if season.peak_rating is not None:
        profile.peak_rating = season.peak_rating
    if season.peak_score is not None:
        profile.peak_score = season.peak_score


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else payload


def _parse_battle_detail(
    payload: dict[str, Any], target_role_id: str
) -> dict[str, Any]:
    """从对局详情里抽出双方十人面板，并标出目标玩家。"""
    data = _unwrap(payload)
    blue = [r for r in _as_list(data.get("blueRoles")) if isinstance(r, dict)]
    red = [r for r in _as_list(data.get("redRoles")) if isinstance(r, dict)]

    def to_row(role: dict[str, Any], index: int) -> dict[str, Any]:
        basic = _as_dict(role.get("basicInfo"))
        stats = _as_dict(role.get("battleStats"))
        records = _as_dict(role.get("battleRecords"))
        used_hero = _as_dict(records.get("usedHero")) or _as_dict(basic.get("usedHero"))
        equipment = [
            {
                "id": str(item.get("equipId") or ""),
                "name": str(item.get("equipName") or ""),
                "icon": str(item.get("equipIcon") or ""),
            }
            for item in _as_list(records.get("finalEquips"))
            if isinstance(item, dict)
            and (item.get("equipId") or item.get("equipName") or item.get("equipIcon"))
        ]
        skill = _as_dict(records.get("skill"))
        role_id = str(basic.get("roleId") or "")
        hero_id = str(
            records.get("heroId")
            or used_hero.get("heroId")
            or basic.get("heroId")
            or ""
        )
        return {
            "index": index,
            "role_id": role_id,
            "nickname": str(basic.get("roleName") or basic.get("nickname") or ""),
            "hero_id": hero_id,
            "hero_name": hero_repository.name(hero_id) if hero_id else "",
            "hero_icon": str(
                records.get("heroIcon") or used_hero.get("heroIcon") or ""
            ),
            "avatar": str(basic.get("roleIcon") or ""),
            "equipment": equipment,
            "skill": {
                "id": str(skill.get("skillId") or ""),
                "name": str(skill.get("skillName") or ""),
                "icon": str(skill.get("skillIcon") or ""),
            },
            "image_resources": collect_image_resources(role),
            "level": int(stats.get("heroLevel", stats.get("level")))
            if stats.get("heroLevel", stats.get("level")) is not None
            else None,
            "kills": int(stats.get("killCnt") or stats.get("killcnt") or 0),
            "deaths": int(stats.get("deadCnt") or stats.get("deadcnt") or 0),
            "assists": int(stats.get("assistCnt") or stats.get("assistcnt") or 0),
            "money": int(stats.get("money") or 0),
            "hurt": int(
                stats.get("totalHeroHurtCnt") or stats.get("totalHurtCnt") or 0
            ),
            "behurt": int(
                stats.get("totalBeheroHurtCnt") or stats.get("totalBehurtCnt") or 0
            ),
            "fight_power": int(stats.get("fightPower") or 0),
            "is_target": bool(target_role_id and role_id == target_role_id),
        }

    blue_rows = [to_row(role, i + 1) for i, role in enumerate(blue)]
    red_rows = [to_row(role, i + 1) for i, role in enumerate(red)]
    for rows in (blue_rows, red_rows):
        total_hurt = sum(row["hurt"] for row in rows)
        total_behurt = sum(row["behurt"] for row in rows)
        for row in rows:
            row["hurt_percent"] = (
                round(row["hurt"] / total_hurt * 100, 1) if total_hurt else None
            )
            row["behurt_percent"] = (
                round(row["behurt"] / total_behurt * 100, 1) if total_behurt else None
            )
    return {
        "blue": blue_rows,
        "red": red_rows,
        "has_detail": bool(blue_rows or red_rows),
        "image_resources": collect_image_resources(data),
    }
