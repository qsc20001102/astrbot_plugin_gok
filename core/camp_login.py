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
import hashlib
import json
import random
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

__all__ = ["CampLoginManager", "CampLoginSession", "QR_SESSION_TTL_SECONDS"]

APPID_WX = "wxf4b1e8a3e9aaf978"
CAMP_BASE_URL = "https://ssl.kohsocialapp.qq.com:10001"
WX_QR_URL = "https://open.weixin.qq.com/connect/sdk/qrconnect"
WX_POLL_URL = "https://long.open.weixin.qq.com/connect/l/qrconnect"

QR_SESSION_TTL_SECONDS = 300

COMMON_HEADERS: dict[str, str] = {
    "Content-Encrypt": "",
    "Accept-Encrypt": "",
    "NOENCRYPT": "1",
    "X-Client-Proto": "https",
    "User-Agent": "okhttp/4.9.1",
}

# 客户端指纹（营地 Android 客户端常量），登录时同时用于请求头与表单。
CLIENT_HEADERS: dict[str, str] = {
    "cChannelId": "10003391",
    "cClientVersionCode": "2057957801",
    "cClientVersionName": "10.111.0323",
    "cCurrentGameId": "20001",
    "cGameId": "20001",
    "cGzip": "1",
    "cIsArm64": "true",
    "cSupportArm64": "true",
    "cSystem": "android",
    "cSystemVersionCode": "34",
    "cSystemVersionName": "14",
    "cpuHardware": "qcom",
    "gameId": "20001",
    "tinkerId": "2057957801_64_0",
}


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

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at - time.time()))

    @property
    def qrcode_mime(self) -> str:
        """二维码实际图片类型 —— 微信返回的是 JPEG，不是 PNG。"""
        return detect_image_mime(self.qrcode_base64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
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


def _build_nonce(length: int = 8) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def _build_device_payload() -> dict[str, Any]:
    """构造登录用的设备指纹 JSON。"""
    timestamp = int(time.time() * 1000)
    device_id = secrets.token_hex(16)
    nonce = f":{secrets.token_hex(16)}:{timestamp}"
    return {
        "timestamp": timestamp,
        "nonce": nonce,
        "cDeviceId": device_id,
        "deviceid": device_id,
        "cDeviceImei": device_id[:15],
        "cDeviceMac": "02:00:00:00:00:00",
        "cDevicePPI": 480,
        "cDeviceScreenWidth": 1080,
        "cDeviceScreenHeight": 2400,
        "cDeviceBrand": "OnePlus",
        "cDeviceModel": "PHK110",
        "cDeviceMem": 12 * 1024 * 1024 * 1024,
        "cDeviceCPU": "SM8650",
        "cSystemVersionCode": "34",
        "cDeviceNet": "WIFI",
        "cDeviceSP": "China Mobile",
        "cDeviceOaid": device_id,
        "deviceLevel": 3,
        "px": 0,
        "py": 0,
        "wifi_ssid": "unknown",
        "wifi_mac": "02:00:00:00:00:00",
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# Share transient login state between managers in the same loaded module.
# Refreshing the page can resume it; restarting/reloading the module cannot.
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


class CampLoginManager:
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

    def list_sessions(self) -> list[CampLoginSession]:
        return active_sessions()

    # ------------------------------------------------------------------ 步骤实现
    async def _fetch_sdk_ticket(self, x_log_uid: str) -> tuple[str, str]:
        """返回 (sdkTicket, 错误信息)。"""
        response = await self.http.request(
            "POST",
            f"{CAMP_BASE_URL}/a/getwxsdkticket",
            headers={**COMMON_HEADERS, "x-log-uid": x_log_uid},
        )
        if not response.ok:
            return "", response.error or f"HTTP {response.status}"
        payload = response.json() or {}
        if payload.get("returnCode") != 0:
            return "", str(payload.get("returnMsg") or "获取 sdkTicket 失败")
        ticket = str((payload.get("data") or {}).get("sdkTicket") or "")
        if not ticket:
            return "", "获取 sdkTicket 失败：响应缺少 sdkTicket"
        return ticket, ""

    async def _fetch_qrcode(self, ticket: str) -> tuple[dict[str, str] | None, str]:
        nonce = _build_nonce()
        timestamp = str(int(time.time()))
        signature = hashlib.sha1(
            f"appid={APPID_WX}&noncestr={nonce}&sdk_ticket={ticket}&timestamp={timestamp}".encode()
        ).hexdigest()
        query = urllib.parse.urlencode(
            {
                "appid": APPID_WX,
                "noncestr": nonce,
                "timestamp": timestamp,
                "scope": "snsapi_userinfo",
                "signature": signature,
            }
        )
        response = await self.http.request("GET", f"{WX_QR_URL}?{query}")
        if not response.ok:
            return None, response.error or f"HTTP {response.status}"
        payload = response.json() or {}
        if payload.get("errcode") != 0:
            return None, str(payload.get("errmsg") or "获取二维码失败")
        qr_uuid = str(payload.get("uuid") or "")
        qrcode = str((payload.get("qrcode") or {}).get("qrcodebase64") or "")
        if not qr_uuid or not qrcode:
            return None, "获取二维码失败：响应不完整"
        return {"uuid": qr_uuid, "qrcode_base64": qrcode}, ""

    async def _poll_wechat(self, qr_uuid: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"f": "json", "uuid": qr_uuid})
        response = await self.http.request("GET", f"{WX_POLL_URL}?{query}", timeout=35)
        if not response.ok:
            return {"error": response.error or f"HTTP {response.status}"}
        payload = response.json()
        if not isinstance(payload, dict):
            return {"error": "微信登录服务返回格式异常，请稍后重试"}
        return payload

    async def _login_with_code(
        self, code: str, x_log_uid: str
    ) -> tuple[dict[str, Any] | None, str]:
        """用微信 authCode 换取营地登录态。"""
        # 登录用的 specialEncodeParam 必须携带完整设备指纹（与查询接口的简版不同）。
        device_payload = json.dumps(_build_device_payload(), separators=(",", ":"))
        special_encode_param = base64.b64encode(
            rsa_encrypt_chunked(device_payload.encode("utf-8"), self.public_key)
        ).decode("ascii")

        form = {
            "loginType": "wx",
            "code": code,
            "delOldUser": "0",
            "key1": secrets.token_hex(16),
            "lastLoginTime": "0",
            "lastGetRemarkTime": "0",
            "cChannelId": "10003391",
            "cClientVersionCode": "2057957801",
            "cClientVersionName": "10.111.0323",
            "cCurrentGameId": "20001",
            "cGameId": "20001",
            "cGzip": "1",
            "cIsArm64": "true",
            "cRand": str(int(time.time() * 1000)),
            "cSupportArm64": "true",
            "cSystem": "android",
            "cSystemVersionCode": "34",
            "cSystemVersionName": "14",
            "cpuHardware": "qcom",
            "gameId": "20001",
            "tinkerId": "2057957801_64_0",
            "specialEncodeParam": special_encode_param,
        }
        headers = {
            **COMMON_HEADERS,
            **CLIENT_HEADERS,
            "x-log-uid": x_log_uid,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "cRand": str(int(time.time() * 1000)),
            "specialEncodeParam": special_encode_param,
        }
        response = await self.http.request(
            "POST",
            f"{CAMP_BASE_URL}/user/login",
            headers=headers,
            data=urllib.parse.urlencode(form),
        )
        if not response.ok:
            return None, response.error or f"HTTP {response.status}"
        payload = response.json() or {}
        if payload.get("returnCode") != 0:
            return None, str(payload.get("returnMsg") or "营地登录失败")
        data = payload.get("data") or {}
        if not data.get("userId") or not data.get("token"):
            return None, "营地登录失败：缺少 userId 或 token"
        return data, ""

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
    async def create_session(self) -> tuple[CampLoginSession | None, str]:
        """新建一次扫码会话；返回 (会话, 错误信息)。"""
        _prune_sessions()
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
        """Poll one login attempt and persist credentials before reporting success.

        Args:
            task_id: Identifier returned when creating the QR code.

        Returns:
            Login status, with a terminal flag for completed attempts. Repeated
            polls return the same outcome without redeeming the code again.
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

            # Keep the redeemed account if saving fails, so a retry only writes
            # credentials instead of redeeming the single-use WeChat code again.
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
