"""轻量 aiohttp 客户端：单会话复用、超时、统一返回结构。

营地接口的响应体既可能是 JSON，也可能是 XXTEA 密文，且关键状态放在响应头里，
因此这里返回「状态码 + 响应头 + 原始文本」，由上层决定如何解析。
"""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Mapping
from typing import Any

import aiohttp

__all__ = ["HttpResponse", "HttpClient"]

# 单个响应体上限，防止异常上游把内存打满。
MAX_BODY_BYTES = 32 * 1024 * 1024


class HttpResponse:
    """一次 HTTP 调用的结果。"""

    __slots__ = ("status", "headers", "text", "error")

    def __init__(
        self,
        status: int | None,
        headers: Mapping[str, str] | None = None,
        text: str = "",
        error: str = "",
    ) -> None:
        self.status = status
        self.headers: dict[str, str] = {
            k.lower(): v for k, v in (headers or {}).items()
        }
        self.text = text
        self.error = error

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)

    def json(self) -> Any:
        import json

        try:
            return json.loads(self.text)
        except (ValueError, TypeError):
            return None

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<HttpResponse status={self.status} len={len(self.text)} error={self.error!r}>"


class HttpClient:
    """共享一个 ClientSession 的异步 HTTP 客户端。"""

    def __init__(
        self,
        timeout: float = 15.0,
        verify_ssl: bool = True,
        user_agent: str = "okhttp/4.9.1",
    ) -> None:
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        async with self._lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(ssl=self._build_ssl())
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    connector=connector,
                )
        return self._session

    def _build_ssl(self) -> ssl.SSLContext | bool:
        if self.verify_ssl:
            return True
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and not session.closed:
            await session.close()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """发起请求，永不抛异常；失败时在 `HttpResponse.error` 中给出原因。"""
        session = await self._get_session()
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)
        request_timeout = aiohttp.ClientTimeout(
            total=self.timeout if timeout is None else timeout
        )
        try:
            async with session.request(
                method.upper(),
                url,
                headers=request_headers,
                params=params,
                json=json_body,
                data=data,
                timeout=request_timeout,
            ) as response:
                # read(n) can return a single partial network chunk before EOF.
                # Consume the full stream, enforcing the cap across all chunks.
                raw = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if len(raw) + len(chunk) > MAX_BODY_BYTES:
                        return HttpResponse(None, error="接口响应超过大小限制")
                    raw.extend(chunk)
                return HttpResponse(
                    response.status,
                    dict(response.headers),
                    raw.decode("utf-8", "replace"),
                )
        except asyncio.TimeoutError:
            return HttpResponse(None, error="请求超时")
        except aiohttp.ClientError as exc:
            return HttpResponse(None, error=f"网络错误：{type(exc).__name__}")
        except Exception as exc:  # noqa: BLE001 - 兜底，绝不外抛
            return HttpResponse(None, error=f"未知错误：{type(exc).__name__}")
