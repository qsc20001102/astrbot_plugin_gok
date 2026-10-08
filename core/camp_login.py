"""微信扫码登录王者营地：获取并轮询二维码，最终换到营地登录态。

流程（与参考实现 `src/lib/camp/wechat-login.ts` 一致，已在实机验证可达）：

1. `POST https://ssl.kohsocialapp.qq.com:10001/a/getwxsdkticket` → `sdkTicket`
2. `GET  https://open.weixin.qq.com/connect/sdk/qrconnect` → `uuid` + `qrcodebase64`
   （签名 = sha1(`appid=..&noncestr=..&sdk_ticket=..&timestamp=..`)）
3. `GET  https://long.open.weixin.qq.com/connect/l/qrconnect` 轮询 `wx_errcode`
   404=已扫码待确认，405=已确认（返回 `wx_code`），402=过期，403=取消
4. `POST https://ssl.kohsocialapp.qq.com:10001/user/login` → `userId`/`token`/`encodeRes`

登录成功后 `userKey` 由 `encodeRes` 用营地公钥解出，后续所有查询接口都依赖它。
"""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from .camp_auth import CampAccount, CampAuthStore
from .camp_crypto import (
    DEFAULT_PUBLIC_KEY,
    decode_encode_res,
    rsa_encrypt_chunked,
)
from .http import HttpClient
from .login_protocol import (
    CAMP_BASE_URL,
    CLIENT_HEADERS,
    COMMON_HEADERS,
    _build_device_payload,
)
from .login_qq import QQLoginFlow, exchange_qq_code
from .login_wechat import WechatLoginProtocol

__all__ = ["CampLoginManager", "CampLoginSession", "QR_SESSION_TTL_SECONDS"]


QR_SESSION_TTL_SECONDS = 300


# 客户端指纹（营地 Android 客户端常量），登录时同时用于请求头与表单。


@dataclass
class CampLoginSession:
    """一次扫码登录会话。"""

    task_id: str
    x_log_uid: str
    uuid: str
    qrcode_base64: str
    created_at: float
    expires_at: float
    account: CampAccount | None = field(default=None, repr=False)
    result: dict[str, Any] | None = field(default=None, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    platform: str = "wechat"
    qq_flow: QQLoginFlow | None = field(default=None, repr=False)
    creation_task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at - time.time()))

    @property
    def qrcode_mime(self) -> str:
        """二维码实际图片类型 —— 微信返回的是 JPEG，不是 PNG。"""
        return (
            "image/png"
            if self.platform == "qq"
            else detect_image_mime(self.qrcode_base64)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "platform": self.platform,
            "qrcode_base64": self.qrcode_base64,
            "qrcode_mime": self.qrcode_mime,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "remaining_seconds": self.remaining_seconds,
        }


def detect_image_mime(base64_data: str) -> str:
    """按 base64 头部魔数判断图片类型，供前端拼 data URI。"""
    head = (base64_data or "")[:8]
    if head.startswith("/9j/"):
        return "image/jpeg"
    if head.startswith("iVBOR"):
        return "image/png"
    if head.startswith("R0lGOD"):
        return "image/gif"
    if head.startswith("UklGR"):
        return "image/webp"
    return "image/jpeg"


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# 同一模块实例内共享临时登录会话，使页面刷新后可以恢复。
# 进程重启或插件重载后不会恢复这份内存会话。
_SESSIONS: dict[str, CampLoginSession] = {}


def _prune_sessions() -> None:
    for task_id in [
        k
        for k, v in _SESSIONS.items()
        if v.expired
        and not v.lock.locked()
        and (v.account is None or v.result is not None)
    ]:
        _SESSIONS.pop(task_id, None)


def active_sessions() -> list[CampLoginSession]:
    """当前仍在有效期内的扫码会话（按创建时间倒序）。"""
    _prune_sessions()
    return sorted(
        (s for s in _SESSIONS.values() if s.result is None),
        key=lambda s: s.created_at,
        reverse=True,
    )


class CampLoginManager(WechatLoginProtocol):
    """管理扫码会话并完成登录换票。"""

    def __init__(
        self,
        http: HttpClient,
        public_key: str = DEFAULT_PUBLIC_KEY,
        *,
        auth_store: CampAuthStore | None = None,
    ) -> None:
        self.http = http
        self.public_key = public_key
        self.auth_store = auth_store

    # ------------------------------------------------------------------ 会话管理
    def get_session(self, task_id: str) -> CampLoginSession | None:
        return _SESSIONS.get(task_id)

    def drop_session(self, task_id: str) -> None:
        session = _SESSIONS.pop(task_id, None)
        if session is not None:
            session.result = {
                "status": "canceled",
                "message": "已取消登录",
                "terminal": True,
            }
            if session.qq_flow:
                if session.creation_task and not session.creation_task.done():
                    session.creation_task.cancel()
                asyncio.create_task(session.qq_flow.close())

    def list_sessions(self) -> list[CampLoginSession]:
        return active_sessions()

    # ------------------------------------------------------------------ 步骤实现

    @staticmethod
    def build_account(
        data: dict[str, Any], x_log_uid: str, public_key: str
    ) -> CampAccount:
        """把登录响应整理成可持久化的账号对象。"""
        encode_res = str(data.get("encodeRes") or "")
        return CampAccount(
            user_id=str(data.get("userId") or ""),
            token=str(data.get("token") or ""),
            user_key=decode_encode_res(encode_res, public_key),
            encode_res=encode_res,
            open_id=str(data.get("openId") or data.get("appOpenid") or ""),
            game_open_id=str(data.get("gameOpenId") or ""),
            game_role_id=str(data.get("gameRoleId") or ""),
            game_server_id=str(data.get("gameServerId") or ""),
            access_token=str(data.get("accessToken") or ""),
            refresh_token=str(data.get("refreshToken") or ""),
            app_openid=str(data.get("appOpenid") or ""),
            avatar=str(data.get("avatar") or ""),
            nickname=str(data.get("nickname") or ""),
            sns_nickname=str(data.get("snsnickname") or ""),
            expires=str(data.get("expires") or ""),
            login_platform="wechat",
            last_login_at=_iso_now(),
            x_log_uid=x_log_uid,
            public_key=public_key,
        )

    # ------------------------------------------------------------------ 对外接口
    async def create_session(
        self, platform: str = "wechat"
    ) -> tuple[CampLoginSession | None, str]:
        """新建一次扫码会话；返回 (会话, 错误信息)。"""
        _prune_sessions()
        if platform not in {"wechat", "qq"}:
            return None, "登录方式只支持微信或 QQ"
        if len(active_sessions()) >= 4:
            return None, "进行中的扫码会话过多，请先取消旧会话"
        if platform == "qq":
            flow = QQLoginFlow()
            now = time.time()
            session = CampLoginSession(
                secrets.token_urlsafe(16),
                str(uuid.uuid4()).upper(),
                "",
                "",
                now,
                now + 180,
                platform="qq",
                qq_flow=flow,
            )
            _SESSIONS[session.task_id] = session
            session.creation_task = asyncio.create_task(self._prepare_qq(session))
            return session, ""
        x_log_uid = str(uuid.uuid4()).upper()
        ticket, error = await self._fetch_sdk_ticket(x_log_uid)
        if not ticket:
            logger.warning("获取登录 sdkTicket 失败：%s", error)
            return None, error

        qr, error = await self._fetch_qrcode(ticket)
        if not qr:
            logger.warning("获取登录二维码失败：%s", error)
            return None, error

        now = time.time()
        session = CampLoginSession(
            task_id=secrets.token_urlsafe(16),
            x_log_uid=x_log_uid,
            uuid=qr["uuid"],
            qrcode_base64=qr["qrcode_base64"],
            created_at=now,
            expires_at=now + QR_SESSION_TTL_SECONDS,
        )
        _SESSIONS[session.task_id] = session
        logger.info("已创建营地扫码登录会话：%s", session.task_id[:8])
        return session, ""

    async def poll(self, task_id: str) -> dict[str, Any]:
        """轮询扫码结果，先保存凭据再报告成功。

        Args:
            task_id: 创建扫码会话时返回的标识。

        Returns:
            带终态标记的登录结果；重复轮询不再次兑换授权码。
        """
        session = self.get_session(task_id)
        if session is None:
            return {
                "status": "expired",
                "message": "登录会话已不存在（页面可能被刷新或插件被重载），请重新获取二维码",
                "terminal": True,
            }
        async with session.lock:
            if session.result is not None:
                return session.result
            if session.expired and session.account is None:
                session.result = {
                    "status": "expired",
                    "message": "二维码已超过有效期，请重新获取",
                    "terminal": True,
                }
                return session.result

            if session.account is None:
                if session.platform == "qq":
                    return await self._poll_qq(session)
                payload = await self._poll_wechat(session.uuid)
                if session.result is not None:
                    return session.result
                if payload.get("error"):
                    return {"status": "error", "message": str(payload["error"])}
                try:
                    status_code = int(payload.get("wx_errcode"))
                except (TypeError, ValueError):
                    return {
                        "status": "error",
                        "message": "微信未返回有效扫码状态，正在重试",
                    }
                wx_code = str(payload.get("wx_code") or "")
                if status_code == 405 and wx_code:
                    data, error = await self._login_with_code(
                        wx_code, session.x_log_uid
                    )
                    if session.result is not None:
                        return session.result
                    if data:
                        try:
                            session.account = self.build_account(
                                data, session.x_log_uid, self.public_key
                            )
                            if not session.account.resolve_user_key():
                                error = "营地登录响应缺少有效 userKey，请重新扫码登录"
                        except (ValueError, TypeError):
                            error = "营地登录响应的安全参数无法解析，请重新扫码登录"
                    if error or session.account is None or not session.account.ready:
                        session.result = {
                            "status": "error",
                            "message": error or "营地登录态不完整，请重新扫码登录",
                            "terminal": True,
                        }
                        return session.result
                elif status_code in {402, 403}:
                    session.result = {
                        "status": "expired" if status_code == 402 else "canceled",
                        "message": "二维码已过期，请重新获取"
                        if status_code == 402
                        else "已取消登录",
                        "terminal": True,
                    }
                    return session.result
                elif status_code == 404:
                    return {"status": "scanned", "message": "已扫码，请在微信中确认"}
                elif status_code == 408:
                    return {"status": "waiting", "message": "等待扫码"}
                else:
                    return {
                        "status": "error",
                        "message": f"微信扫码状态异常({status_code})，正在重试",
                    }

            # 保存失败时保留已兑换的账号，下一次仅重试写入，
            # 不重复兑换只能使用一次的微信授权码。
            if self.auth_store is not None:
                try:
                    await self.auth_store.upsert(session.account)
                except (OSError, ValueError) as exc:
                    logger.exception("保存营地登录态失败")
                    return {
                        "status": "error",
                        "message": f"保存登录态失败({type(exc).__name__})，正在重试",
                    }
            session.result = {
                "status": "success",
                "account": session.account,
                "terminal": True,
            }
            session.expires_at = max(session.expires_at, time.time() + 60)
            logger.info("营地扫码登录完成：%s", session.account.display_name)
            return session.result

    async def _poll_qq(self, session: CampLoginSession) -> dict[str, Any]:
        """在会话锁内完成 QQ 换票，并先保存账号再向页面报告成功。"""
        if not session.qq_flow:
            return {"status": "expired", "message": "QQ 会话已不存在", "terminal": True}
        if session.creation_task and not session.creation_task.done():
            return {"status": "preparing", "message": "正在准备 QQ 登录二维码"}
        progress = await session.qq_flow.poll()
        if progress.get("status") != "authorized":
            if progress.get("terminal"):
                session.result = progress
                await session.qq_flow.close()
            return {
                **progress,
                "platform": "qq",
                "qrcode_base64": session.qrcode_base64,
                "qrcode_mime": session.qrcode_mime,
                "expires_in": session.remaining_seconds,
            }
        try:
            tokens = await exchange_qq_code(self.http, progress["code"])
            if session.result is not None:
                return session.result
            data = await self._login_qq(tokens, session.x_log_uid)
            if session.result is not None:
                return session.result
            data = {
                **data,
                "accessToken": tokens["accessToken"],
                "refreshToken": tokens.get("refreshToken", ""),
            }
            session.account = self.build_account(
                data, session.x_log_uid, self.public_key
            )
            session.account.login_platform = "qq"
            if not session.account.ready or not session.account.resolve_user_key():
                raise ValueError("QQ 营地登录响应缺少有效安全参数，请重新扫码")
        except (ValueError, TypeError) as exc:
            session.result = {"status": "error", "message": str(exc), "terminal": True}
            session.account = None
            return session.result
        finally:
            await session.qq_flow.close()
        # 下一次 poll 会复用已换到的账号，仅重试持久化，不再次兑换单次授权码。
        if self.auth_store is not None:
            try:
                await self.auth_store.upsert(session.account)
            except (OSError, ValueError):
                return {
                    "status": "error",
                    "message": "保存登录态失败，请重试",
                    "terminal": False,
                }
        session.result = {
            "status": "success",
            "account": session.account,
            "terminal": True,
        }
        return session.result

    async def _prepare_qq(self, session: CampLoginSession) -> None:
        """后台准备二维码，避免浏览器启动超过宿主页面请求时限。"""
        assert session.qq_flow is not None
        try:
            image = await session.qq_flow.start(ttl_seconds=180)
            if session.result is not None:
                await session.qq_flow.close()
                return
            session.qrcode_base64 = image
            session.created_at = time.time()
            session.expires_at = session.created_at + 180
        except asyncio.CancelledError:
            await session.qq_flow.close()
            raise
        except Exception as exc:
            session.result = {
                "status": "error",
                "message": str(exc)
                if isinstance(exc, RuntimeError)
                else "QQ 二维码准备失败，请稍后重试",
                "terminal": True,
            }
            await session.qq_flow.close()

    async def _login_qq(self, tokens: dict[str, Any], x_log_uid: str) -> dict[str, Any]:
        """使用 QQ 平台凭据调用营地 openSdk 登录分支。"""
        device_payload = json.dumps(_build_device_payload(), separators=(",", ":"))
        special = base64.b64encode(
            rsa_encrypt_chunked(device_payload.encode("utf-8"), self.public_key)
        ).decode("ascii")
        form = {
            **CLIENT_HEADERS,
            "cClientVersionCode": "2057971306",
            "cClientVersionName": "10.114.0826",
            "cSystemVersionCode": "35",
            "cSystemVersionName": "15",
            "tinkerId": "2057971306_64_0",
            "cRand": str(int(time.time() * 1000)),
            "delOldUser": "0",
            "key1": secrets.token_hex(16),
            "lastLoginTime": "0",
            "lastGetRemarkTime": "0",
            "specialEncodeParam": special,
            "loginType": "openSdk",
            "accessToken": str(tokens["accessToken"]),
            "openId": str(tokens["openID"]),
            "payToken": str(tokens.get("payToken") or ""),
        }
        response = await self.http.request(
            "POST",
            f"{CAMP_BASE_URL}/user/login",
            headers={
                **COMMON_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "x-log-uid": x_log_uid,
            },
            data=urllib.parse.urlencode(form),
        )
        payload = response.json() or {}
        if not isinstance(payload, dict):
            raise ValueError("QQ 营地登录响应格式异常，请重新扫码")
        data = payload.get("data")
        if (
            not response.ok
            or payload.get("returnCode") != 0
            or not isinstance(data, dict)
            or not data.get("userId")
            or not data.get("token")
        ):
            raise ValueError("QQ 营地登录失败，请重新扫码")
        return data

    async def close(self) -> None:
        """插件停用时取消扫码，并回收仍然打开的 QQ 浏览器会话。"""
        sessions = tuple(_SESSIONS.values())
        for session in sessions:
            if session.result is None:
                session.result = {
                    "status": "canceled",
                    "message": "插件已停用",
                    "terminal": True,
                }
            if session.creation_task and not session.creation_task.done():
                session.creation_task.cancel()
        await asyncio.gather(
            *(session.creation_task for session in sessions if session.creation_task),
            return_exceptions=True,
        )
        await asyncio.gather(
            *(session.qq_flow.close() for session in sessions if session.qq_flow),
            return_exceptions=True,
        )
        _SESSIONS.clear()
