"""营地数据接口客户端：向 `kohcamp.qq.com` 发请求并处理加密/错误码/换号重试。

请求头里最关键的是 `encodeParam`（用 userKey 做 XXTEA 的 `{timestamp, nonce}`）；
响应若带 `campencrypt: true` 则需用同一个 userKey 解密响应体。

错误码约定：`-10107` 玩家隐藏战绩；`-30107` 或文案含"频繁"为频控；
出现鉴权类文案（登录/token/安全参数等）视为登录态失效 —— 三种情况都会换账号重试。
"""

from __future__ import annotations

import asyncio
import json
import secrets
import urllib.parse
from time import time
from typing import Any

from astrbot.api import logger

from .camp_auth import CampAccount, CampAuthStore
from .camp_crypto import (
    build_encode_param,
    build_special_encode_param,
    decode_camp_payload,
)
from .camp_search import parse_search_response
from .http import HttpClient

__all__ = ["CampApiError", "CampClient", "MAIN_BASE"]

MAIN_BASE = "https://kohcamp.qq.com"

# 客户端常量（与营地 Android 客户端一致）。
DEFAULT_USER_AGENT = "okhttp/4.9.1"
CHANNEL_ID = "10003391"
CLIENT_VERSION_CODE = "2057957801"
CLIENT_VERSION_NAME = "10.111.0323"
GAME_ID = "20001"
TINKER_ID = "2057957801_64_0"

_RATE_LIMIT_CODES = {-30107}
_HIDDEN_CODES = {-10107}
_AUTH_KEYWORDS = ("登录", "登录态", "token", "鉴权", "安全参数", "重新登录")
_RATE_KEYWORDS = ("操作频繁", "请求频繁", "访问频繁")


class CampApiError(Exception):
    """营地接口错误，`code` 用于上层决定是否换号或给出针对性提示。"""

    def __init__(self, message: str, code: str = "upstream") -> None:
        super().__init__(message)
        self.code = code

    @property
    def retryable(self) -> bool:
        return self.code in {"auth", "rate_limit"}


def _build_traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def _now_ms() -> int:
    return int(time() * 1000)


class CampClient:
    """带账号池与自动换号的营地接口客户端。"""

    def __init__(self, http: HttpClient, auth_store: CampAuthStore) -> None:
        self.http = http
        self.auth_store = auth_store
        self._validation_lock = asyncio.Lock()

    # ------------------------------------------------------------------ 请求头
    @staticmethod
    def _build_headers(account: CampAccount) -> dict[str, str]:
        user_key = account.resolve_user_key()
        user_id = account.user_id
        headers: dict[str, str] = {
            "Host": "kohcamp.qq.com",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-Encrypt": "",
            "Accept-Encrypt": "",
            "NOENCRYPT": "1",
            "X-Client-Proto": "https",
            "x-log-uid": account.x_log_uid or secrets.token_hex(16).upper(),
            "traceparent": _build_traceparent(),
            "istrpcrequest": "true",
            "cchannelid": CHANNEL_ID,
            "cclientversioncode": CLIENT_VERSION_CODE,
            "cclientversionname": CLIENT_VERSION_NAME,
            "ccurrentgameid": GAME_ID,
            "cgameid": GAME_ID,
            "cgzip": "1",
            "cisarm64": "true",
            # 与营地客户端一致：crand 用当前毫秒时间戳
            "crand": str(_now_ms()),
            "csupportarm64": "true",
            "csystem": "android",
            "csystemversioncode": "34",
            "csystemversionname": "14",
            "cpuhardware": "qcom",
            "gameareaid": "1",
            "gameid": GAME_ID,
            "gameusersex": "1",
            "tinkerid": TINKER_ID,
            "token": account.token,
            "userid": user_id,
            "kohdimgender": "2",
        }
        if account.open_id:
            headers["openid"] = account.open_id
        if account.game_open_id:
            headers["gameopenid"] = account.game_open_id
        if account.game_role_id:
            headers["gameroleid"] = account.game_role_id
        if account.game_server_id:
            headers["gameserverid"] = account.game_server_id

        encode_param = build_encode_param(user_id, user_key)
        if encode_param:
            headers["encodeParam"] = encode_param
        else:
            headers["specialEncodeParam"] = build_special_encode_param()
        return headers

    # ------------------------------------------------------------------ 响应解析
    @staticmethod
    def _parse_response(
        response, account: CampAccount, *, protobuf: bool = False
    ) -> dict[str, Any]:
        encrypt_error = response.header("encryptparamerr")
        if encrypt_error:
            raise CampApiError(
                f"营地安全参数校验失败({encrypt_error})，请重新扫码登录", "auth"
            )

        return_code_header = response.header("returncode")
        if protobuf:
            if return_code_header and _as_int(return_code_header) not in (0, 200):
                return {
                    "returnCode": _as_int(return_code_header),
                    "returnMsg": _decode_header(response.header("returnmsg")),
                }
            try:
                body = response.body
                if response.header("campencrypt").lower() == "true":
                    body = decode_camp_payload(
                        response.text, account.resolve_user_key(), binary=True
                    )
                assert isinstance(body, bytes)
                if body.lstrip().startswith(b"{"):
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid Camp error response")
                    return payload
                return parse_search_response(body)
            except (ValueError, TypeError, AssertionError) as exc:
                raise CampApiError(
                    "营地昵称搜索响应无法解析，请稍后重试", "upstream"
                ) from exc

        payload_text = response.text
        if response.header("campencrypt").lower() == "true":
            user_key = account.resolve_user_key()
            try:
                payload_text = decode_camp_payload(response.text, user_key)
            except (ValueError, TypeError) as exc:
                raise CampApiError(
                    f"营地响应解密失败({type(exc).__name__})，请稍后重试", "upstream"
                ) from exc

        if not payload_text.strip() and return_code_header:
            return {
                "returnCode": _as_int(return_code_header),
                "returnMsg": _decode_header(response.header("returnmsg")),
            }

        try:
            data = json.loads(payload_text)
        except (ValueError, TypeError) as exc:
            raise CampApiError("营地接口返回无法解析，请稍后重试", "upstream") from exc
        if not isinstance(data, dict):
            raise CampApiError("营地接口返回格式异常", "upstream")
        return data

    @staticmethod
    def _raise_for_business_error(data: dict[str, Any]) -> None:
        message = str(
            data.get("returnMsg") or data.get("message") or data.get("msg") or ""
        )
        if message and any(k in message for k in _AUTH_KEYWORDS):
            raise CampApiError(message or "营地登录态已失效，请重新扫码登录", "auth")

        try:
            code = int(data.get("returnCode") or 0)
        except (TypeError, ValueError):
            code = 0

        if code in _HIDDEN_CODES:
            raise CampApiError(
                "该召唤师隐藏了个人战绩，请让对方在王者营地开放战绩后重试", "hidden"
            )
        if code in _RATE_LIMIT_CODES or any(k in message for k in _RATE_KEYWORDS):
            raise CampApiError("操作频繁，请稍后重试", "rate_limit")
        if code not in (0, 200):
            raise CampApiError(message or f"营地接口错误({code})", "upstream")

    # ------------------------------------------------------------------ 核心请求
    async def _request_once(
        self,
        account: CampAccount,
        endpoint: str,
        body: dict[str, Any] | bytes,
        *,
        protobuf: bool = False,
    ) -> dict[str, Any]:
        if not account.ready:
            raise CampApiError("营地登录态不完整，请重新扫码登录", "auth")
        headers = self._build_headers(account)
        if protobuf:
            headers["Content-Type"] = "application/x-protobuf"
        response = await self.http.request(
            "POST",
            f"{MAIN_BASE}{endpoint}",
            headers=headers,
            **({"data": body} if protobuf else {"json_body": body}),
        )
        if response.status is None:
            raise CampApiError(response.error or "营地接口请求失败", "upstream")
        if protobuf and not response.ok:
            raise CampApiError(f"营地接口请求失败(HTTP {response.status})", "upstream")
        data = self._parse_response(response, account, protobuf=protobuf)
        self._raise_for_business_error(data)
        if not response.ok:
            raise CampApiError(f"营地接口请求失败(HTTP {response.status})", "upstream")
        return data

    async def request(
        self, endpoint: str, body: dict[str, Any] | bytes, *, protobuf: bool = False
    ) -> dict[str, Any]:
        """带账号池的请求：遇频控/失效自动冷却当前账号并换号重试。"""
        tried: set[str] = set()
        last_error: CampApiError | None = None

        while True:
            account = await self.auth_store.pick_available(tried)
            if account is None:
                break
            tried.add(account.user_id)
            try:
                return await self._request_once(
                    account, endpoint, body, protobuf=protobuf
                )
            except CampApiError as exc:
                last_error = exc
                if exc.retryable:
                    await self.auth_store.mark_cooldown(account.user_id, exc.code)
                    logger.warning(
                        "营地账号 %s 触发 %s，已冷却并尝试换号",
                        account.user_id[:4] + "***",
                        exc.code,
                    )
                    continue
                raise

        if last_error is not None:
            raise last_error

        accounts = await self.auth_store.list_accounts()
        if accounts:
            if not any(a.ready and not a.auth_invalid for a in accounts):
                raise CampApiError(
                    "营地账号登录态均已失效，请在插件页面重新扫码登录", "auth"
                )
            raise CampApiError(
                "营地账号均处于冷却或不可用，请稍后重试或在插件页面添加新账号",
                "rate_limit",
            )
        raise CampApiError("尚未登录王者营地，请先在插件页面扫码登录", "auth")

    async def validate_accounts(self) -> dict[str, Any]:
        """用各账号自身凭据独立验证，不通过换号掩盖失败。

        Returns:
            逐账号公开检测结果与各状态的统计。
        """
        async with self._validation_lock:
            results = []
            for account in await self.auth_store.list_accounts():
                try:
                    await self._request_once(
                        account,
                        "/game/koh/profile",
                        {
                            "targetUserId": account.user_id,
                            "targetRoleId": "0",
                            "resVersion": "3",
                            "recommendPrivacy": "0",
                            "apiVersion": "2",
                        },
                    )
                    status, message = "valid", "登录态有效"
                except CampApiError as exc:
                    status = {"auth": "invalid", "rate_limit": "rate_limit"}.get(
                        exc.code, "error"
                    )
                    message = str(exc)
                except (ValueError, TypeError):
                    status, message = "invalid", "登录态的安全参数无效，请重新扫码登录"
                if not await self.auth_store.record_validation(
                    account, status, message
                ):
                    status, message = (
                        "changed",
                        "检测期间账号已删除或重新登录，请重新检测",
                    )
                results.append(
                    {
                        "user_id": account.user_id,
                        "nickname": account.display_name,
                        "status": status,
                        "message": message,
                    }
                )
            return {
                "checked": len(results),
                "valid": sum(r["status"] == "valid" for r in results),
                "invalid": sum(r["status"] == "invalid" for r in results),
                "uncertain": sum(
                    r["status"] not in {"valid", "invalid"} for r in results
                ),
                "results": results,
            }


def _as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _decode_header(value: str) -> str:
    try:
        return urllib.parse.unquote(value)
    except (TypeError, ValueError):
        return value
