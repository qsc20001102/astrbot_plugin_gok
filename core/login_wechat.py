"""微信 SDK 出码、轮询和营地换票协议。"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from typing import Any

from .camp_crypto import rsa_encrypt_chunked
from .http import HttpClient
from .login_protocol import (
    APPID_WX,
    CAMP_BASE_URL,
    CLIENT_HEADERS,
    COMMON_HEADERS,
    WX_POLL_URL,
    WX_QR_URL,
    _build_device_payload,
    _build_nonce,
)


class WechatLoginProtocol:
    """协议实现只依赖 HTTP 客户端与公钥，会话由登录管理器统一维护。"""

    http: HttpClient
    public_key: str

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
