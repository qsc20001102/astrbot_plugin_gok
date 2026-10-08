"""营地登录态存储：支持多账号、频控冷却与自动换号。

对应参考实现的 `src/lib/camp/auth-store.ts`。存储为 `camp_auth.json`：

    {"accounts": [ {user_id, token, user_key, encode_res, ...}, ... ]}

设计要点：
* 按 `user_id` upsert，扫码登录不会覆盖其它账号；
* 频控（rate_limit）/ 登录失效（auth）会给该账号打冷却，冷却期内自动换号；
* 文件读写加锁，避免并发请求互相踩踏。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .camp_crypto import DEFAULT_PUBLIC_KEY, decode_encode_res

__all__ = ["CampAccount", "CampAuthStore"]

DEFAULT_COOLDOWN_SECONDS = 300


@dataclass
class CampAccount:
    """一个营地登录账号。"""

    user_id: str = ""
    token: str = ""
    user_key: str = ""
    encode_res: str = ""
    open_id: str = ""
    game_open_id: str = ""
    game_role_id: str = ""
    game_server_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    app_openid: str = ""
    avatar: str = ""
    nickname: str = ""
    sns_nickname: str = ""
    expires: str = ""
    login_platform: str = "wechat"
    last_login_at: str = ""
    x_log_uid: str = ""
    cooled_until: float = 0.0
    last_skip_reason: str = ""
    auth_invalid: bool = False
    validation_status: str = "unchecked"
    validation_message: str = ""
    last_checked_at: float = 0.0
    public_key: str = DEFAULT_PUBLIC_KEY
    extra: dict[str, Any] = field(default_factory=dict)

    # ---------------------------------------------------------------- 状态判断
    @property
    def ready(self) -> bool:
        """登录态是否完整可用。"""
        return bool(self.user_id and self.token and (self.user_key or self.encode_res))

    @property
    def display_name(self) -> str:
        return self.nickname or self.sns_nickname or f"营地{self.user_id}"

    def is_cooled(self, now: float | None = None) -> bool:
        return self.cooled_until > (time.time() if now is None else now)

    def available(self, now: float | None = None) -> bool:
        return self.ready and not self.auth_invalid and not self.is_cooled(now)

    def resolve_user_key(self) -> str:
        """返回 userKey，必要时从 encodeRes 解出并回填。"""
        if self.user_key:
            return self.user_key
        key = decode_encode_res(self.encode_res, self.public_key or DEFAULT_PUBLIC_KEY)
        if key:
            self.user_key = key
        return key

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CampAccount:
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        data = {k: v for k, v in raw.items() if k in known}
        extra = {k: v for k, v in raw.items() if k not in known}
        account = cls(**data)  # type: ignore[arg-type]
        if extra:
            account.extra = extra
        return account

    def public_dict(self) -> dict[str, Any]:
        """给前端用的脱敏视图（不含 token / userKey）。"""
        return {
            "user_id": self.user_id,
            "nickname": self.display_name,
            "avatar": self.avatar,
            "login_platform": self.login_platform,
            "last_login_at": self.last_login_at,
            "expires": self.expires,
            "cooled_until": self.cooled_until,
            "cooled_remaining": max(0, int(self.cooled_until - time.time())),
            "last_skip_reason": self.last_skip_reason,
            "available": self.available(),
            "ready": self.ready,
            "auth_invalid": self.auth_invalid,
            "validation_status": self.validation_status,
            "validation_message": self.validation_message,
            "last_checked_at": self.last_checked_at,
        }


def _mask(value: str, keep_start: int = 3, keep_end: int = 3) -> str:
    if not value:
        return ""
    if len(value) <= keep_start + keep_end:
        return "***"
    return f"{value[:keep_start]}***{value[-keep_end:]}"


class CampAuthStore:
    """营地账号仓库（文件存储 + 异步锁）。"""

    def __init__(
        self,
        path: Path,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- 内部读写
    def _read_sync(self) -> list[CampAccount]:
        try:
            if not self.path.exists():
                return []
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取营地登录态失败：%s", exc)
            return []

        if isinstance(raw, dict) and isinstance(raw.get("accounts"), list):
            items = raw["accounts"]
        elif isinstance(raw, dict):
            items = [raw]  # 兼容旧版单账号格式
        elif isinstance(raw, list):
            items = raw
        else:
            return []

        accounts: list[CampAccount] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            account = CampAccount.from_dict(item)
            if account.user_id:
                accounts.append(account)
        return accounts

    def _write_sync(self, accounts: list[CampAccount]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [a.to_dict() for a in accounts]}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    # ---------------------------------------------------------------- 对外接口
    async def list_accounts(self) -> list[CampAccount]:
        async with self._lock:
            return self._read_sync()

    async def get(self, user_id: str) -> CampAccount | None:
        async with self._lock:
            for account in self._read_sync():
                if account.user_id == user_id:
                    return account
        return None

    async def upsert(self, account: CampAccount) -> CampAccount:
        """扫码登录成功后写入；已存在同 user_id 则合并更新。"""
        if not account.ready:
            raise ValueError("营地登录态不完整，无法保存")
        async with self._lock:
            accounts = self._read_sync()
            account.cooled_until = 0.0
            account.last_skip_reason = ""
            account.auth_invalid = False
            account.validation_status = "unchecked"
            account.validation_message = ""
            account.last_checked_at = 0.0
            for index, existing in enumerate(accounts):
                if existing.user_id == account.user_id:
                    merged = existing.to_dict()
                    merged.update(account.to_dict())
                    accounts[index] = CampAccount.from_dict(merged)
                    break
            else:
                accounts.append(account)
            self._write_sync(accounts)
        logger.info("已保存营地登录账号：%s", _mask(account.user_id))
        return account

    async def remove(self, user_id: str) -> bool:
        async with self._lock:
            accounts = self._read_sync()
            remaining = [a for a in accounts if a.user_id != user_id]
            if len(remaining) == len(accounts):
                return False
            self._write_sync(remaining)
        logger.info("已删除营地登录账号：%s", _mask(user_id))
        return True

    async def clear(self) -> None:
        async with self._lock:
            self.path.unlink(missing_ok=True)

    async def mark_cooldown(
        self, user_id: str, reason: str, duration_seconds: int | None = None
    ) -> None:
        """给账号打冷却；`auth` 原因默认冷却两倍时长。"""
        base = self.cooldown_seconds if duration_seconds is None else duration_seconds
        if reason == "auth" and duration_seconds is None:
            base *= 2
        async with self._lock:
            accounts = self._read_sync()
            for account in accounts:
                if account.user_id == user_id:
                    account.cooled_until = time.time() + base
                    account.last_skip_reason = reason
                    if reason == "auth":
                        account.auth_invalid = True
                        account.validation_status = "invalid"
                        account.validation_message = "登录态已失效，请重新扫码登录"
                    break
            else:
                return
            self._write_sync(accounts)

    async def record_validation(
        self, checked: CampAccount, status: str, message: str
    ) -> bool:
        """仅在被检测凭据仍然有效时保存检测结果。

        Args:
            checked: 发起检测时的账号和凭据快照。
            status: 本次检测得到的状态。
            message: 公开的检测或错误说明。

        Returns:
            凭据仍匹配且结果已保存时为真。
        """
        async with self._lock:
            accounts = self._read_sync()
            account = next((a for a in accounts if a.user_id == checked.user_id), None)
            if (
                account is None
                or account.token != checked.token
                or account.encode_res != checked.encode_res
                or (
                    account.user_key
                    and checked.user_key
                    and account.user_key != checked.user_key
                )
            ):
                return False
            account.validation_status = status
            account.validation_message = message
            account.last_checked_at = time.time()
            if status == "valid":
                account.auth_invalid = False
                account.cooled_until = 0.0
                account.last_skip_reason = ""
            elif status == "invalid":
                account.auth_invalid = True
                account.last_skip_reason = "auth"
            elif status == "rate_limit":
                account.cooled_until = time.time() + self.cooldown_seconds
                account.last_skip_reason = "rate_limit"
            self._write_sync(accounts)
            return True

    async def pick_available(self, exclude: Iterable[str] = ()) -> CampAccount | None:
        """按顺序挑一个可用账号，跳过排除列表与冷却中的账号。"""
        excluded = {str(x) for x in exclude if x}
        async with self._lock:
            accounts = self._read_sync()
        now = time.time()
        for account in accounts:
            if account.user_id in excluded:
                continue
            if account.available(now):
                return account
        return None

    async def summary(self) -> dict[str, Any]:
        """给 Web 页面 / 指令用的账号总览。"""
        accounts = await self.list_accounts()
        now = time.time()
        available = [a for a in accounts if a.available(now)]
        primary = available[0] if available else (accounts[0] if accounts else None)
        return {
            "logged_in": bool(available),
            "count": len(accounts),
            "available_count": len(available),
            "user_id": _mask(primary.user_id) if primary else "",
            "nickname": primary.display_name if primary else "",
            "last_login_at": primary.last_login_at if primary else "",
            "expires": primary.expires if primary else "",
            "accounts": [a.public_dict() for a in accounts],
        }

    async def ensure_user_keys(self) -> None:
        """批量补齐缺失的 userKey（历史数据可能只有 encodeRes）。"""
        async with self._lock:
            accounts = self._read_sync()
            changed = False
            for account in accounts:
                if not account.user_key and account.encode_res:
                    if account.resolve_user_key():
                        changed = True
            if changed:
                self._write_sync(accounts)
