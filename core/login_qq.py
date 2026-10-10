"""QQ 浏览器扫码与 YSDK 换票协议；每个会话独立管理浏览器资源。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from astrbot.api import logger

from .http import HttpClient

QQ_APP_ID = "1105200115"
QQ_LOGIN_URL = (
    "https://openmobile.qq.com/oauth2.0/m_authorize?client_id="
    f"{QQ_APP_ID}&scope=all&redirect_uri=auth://tauth.qq.com/&style=qr&response_type=code"
)
QQ_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; V2366GA Build/V417IR; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/110.0.5481.154 Safari/537.36 tencent_game_emulator"
)
QR_SELECTORS = (
    "#qrlogin_img",
    ".qrlogin_img",
    'img[src*="ptqrshow"]',
    'img[src*="qrcode"]',
    "canvas#qrlogin_canvas",
    ".qrlogin canvas",
)
YSDK_URL = "https://ysdk.qq.com/cmd/QQCodeLogin?"
# 来自公开上游的协议常量，不是用户账号凭据。
YSDK_SIGN_KEY = b"yyb@cloud_game:CQ8FA#"


def capture_auth_code(url: str) -> str:
    """只接受指定 QQ 授权回调，避免从普通 URL 误取 code。

    Args:
        url: 浏览器请求或导航的地址。

    Returns:
        合法回调内的授权码，没有则为空。
    """
    try:
        parsed = urlsplit(url)
        direct_callback = parsed.hostname == "tauth.qq.com" and parsed.scheme in {
            "auth",
            "https",
        }
        # QQ 移动授权页实测会将 auth:// 回调改写为此固定 HTTP 地址。
        # 只兼容完整的固定地址，不放宽到任意域名或包含 tauth 的路径。
        rewritten_callback = (
            parsed.scheme == "http"
            and parsed.netloc == "auth"
            and parsed.path == "//tauth.qq.com/"
        )
        if not (direct_callback or rewritten_callback):
            return ""
        code = parse_qs(parsed.query).get("code", [""])[0]
    except ValueError:
        return ""
    return code if re.fullmatch(r"[0-9A-Za-z]+", code) else ""


def _browser_executable() -> str | None:
    """优先复用系统浏览器，没有时由 Playwright 使用已安装的 Chromium。"""
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        candidate = shutil.which(name)
        if candidate:
            return candidate
    if os.name == "nt":
        for directory in (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ):
            if not directory:
                continue
            for relative in (
                "Microsoft/Edge/Application/msedge.exe",
                "Google/Chrome/Application/chrome.exe",
            ):
                candidate = Path(directory) / relative
                if candidate.is_file():
                    return str(candidate)
    return None


def _safe_error_detail(exc: Exception) -> str:
    """Keep startup diagnostics without logging authorization URLs or secrets."""
    detail = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+", "<URL>", str(exc))
    detail = re.sub(
        r"(?i)\b(code|token|access_token|refresh_token|cookie|authorization)\b"
        r"(\s*[:=]\s*)[^\s,;]+",
        r"\1\2<redacted>",
        detail,
    )
    return detail[:2000]


def _start_error_message(exc: Exception, stage: str) -> str:
    """Translate browser startup and navigation failures into actionable hints."""
    detail = str(exc).lower()
    if stage == "启动浏览器":
        if "executable doesn't exist" in detail or isinstance(exc, FileNotFoundError):
            return (
                "QQ 登录没有可启动的浏览器，请在运行 AstrBot 的同一环境和用户下执行 "
                "python -m playwright install chromium 后重试"
            )
        if any(
            marker in detail
            for marker in (
                "host system is missing dependencies",
                "error while loading shared libraries",
                "cannot open shared object file",
                "missing libraries",
            )
        ):
            return (
                "QQ 登录浏览器缺少 Linux 系统依赖，请在 AstrBot 所在服务器或容器内执行 "
                "python -m playwright install --with-deps chromium 后重试"
            )
        return "QQ 登录浏览器启动失败，请查看 AstrBot 后台的「QQ 登录准备失败」日志"
    if stage == "访问 QQ 登录页":
        network_error = re.search(r"net::(ERR_[A-Z0-9_]+)", str(exc))
        if network_error:
            return (
                f"QQ 登录页访问失败（{network_error[1]}），请检查 AstrBot 所在服务器或容器"
                "到 openmobile.qq.com 的网络、DNS 与证书"
            )
        if "timeout" in detail or isinstance(exc, TimeoutError):
            return (
                "QQ 登录页加载超时，请检查 AstrBot 所在服务器或容器"
                "到 openmobile.qq.com 的网络后重试"
            )
        return "QQ 登录页访问失败，请查看 AstrBot 后台的「QQ 登录准备失败」日志"
    return f"QQ 登录准备失败（{stage}），请查看 AstrBot 后台的「QQ 登录准备失败」日志"


class _QQLoginError(RuntimeError):
    """An actionable message already prepared for the login page."""


class QQLoginFlow:
    """保持从出码到授权回调的同一浏览器会话，不共享 Cookies。"""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._code = ""
        self._closed = False
        self._close_lock = asyncio.Lock()
        self._expiry_task: asyncio.Task | None = None

    def _capture(self, url: str) -> None:
        if not self._code:
            self._code = capture_auth_code(url)

    async def _launch_browser(self) -> Any:
        """Fall back to Playwright Chromium if the detected system browser fails."""
        launch = {"headless": True, "timeout": 30000}
        executable = _browser_executable()
        if executable:
            try:
                return await self._playwright.chromium.launch(
                    **launch, executable_path=executable
                )
            except Exception as exc:
                logger.warning(
                    "QQ 系统浏览器启动失败，尝试 Playwright Chromium（%s）：%s",
                    type(exc).__name__,
                    _safe_error_detail(exc),
                )
        return await self._playwright.chromium.launch(**launch)

    async def start(self, ttl_seconds: int = 180) -> str:
        """打开授权页，读取页面自身的二维码，并设置无人轮询时的清理期限。

        Args:
            ttl_seconds: 取得二维码后的会话有效秒数。

        Returns:
            二维码 PNG 的 Base64，不包含浏览器 Cookie。

        Raises:
            RuntimeError: 浏览器不可用或二维码未加载。
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("QQ 登录依赖尚未安装，请安装插件依赖后重载") from exc
        stage = "启动 Playwright"
        try:
            self._playwright = await async_playwright().start()
            stage = "启动浏览器"
            self._browser = await self._launch_browser()
            stage = "创建登录会话"
            self._context = await self._browser.new_context(
                user_agent=QQ_USER_AGENT,
                viewport={"width": 420, "height": 760},
                is_mobile=True,
            )
            self._context.on("request", lambda request: self._capture(request.url))

            async def intercept_rewritten_callback(route: Any) -> None:
                # 读取真实回调后终止导航，避免访问被 QQ 改写出来的 auth 主机。
                self._capture(route.request.url)
                await route.abort()

            await self._context.route(
                "http://auth//tauth.qq.com/**", intercept_rewritten_callback
            )
            self._page = await self._context.new_page()
            # 深链接可能不触发普通 HTTP 请求，用 Chromium 导航事件补齐回调捕获。
            cdp = await self._context.new_cdp_session(self._page)
            await cdp.send("Page.enable")
            cdp.on(
                "Page.frameRequestedNavigation",
                lambda event: self._capture(event.get("url", "")),
            )
            cdp.on("Page.windowOpen", lambda event: self._capture(event.get("url", "")))
            self._page.on("framenavigated", lambda frame: self._capture(frame.url))
            stage = "访问 QQ 登录页"
            response = await self._page.goto(
                QQ_LOGIN_URL, wait_until="domcontentloaded", timeout=45000
            )
            if response is not None and not response.ok:
                raise _QQLoginError(
                    f"QQ 登录页返回 HTTP {response.status}，请检查服务器或容器网络后重试"
                )
            stage = "读取二维码"
            # 二维码可能出现在子框架中；截图直接来自同一会话内的元素。
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                for frame in self._page.frames:
                    for selector in QR_SELECTORS:
                        locator = frame.locator(selector).first
                        try:
                            box = await locator.bounding_box(timeout=400)
                            if (
                                box
                                and box["width"] > 40
                                and box["height"] > 40
                                and await locator.is_visible()
                            ):
                                image = await locator.screenshot(
                                    type="png", timeout=5000
                                )
                                self._expiry_task = asyncio.create_task(
                                    self._expire(ttl_seconds)
                                )
                                return base64.b64encode(image).decode("ascii")
                        except Exception:
                            # 不同 QQ 页面版本可能不含当前选择器，继续检查其余候选。
                            continue
                await asyncio.sleep(0.5)
            raise _QQLoginError(
                "QQ 登录页已打开，但二维码未能加载，请检查服务器或容器网络后重新获取"
            )
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as exc:
            logger.warning(
                "QQ 登录准备失败（%s/%s）：%s",
                stage,
                type(exc).__name__,
                _safe_error_detail(exc),
            )
            await self.close()
            if isinstance(exc, _QQLoginError):
                raise
            raise RuntimeError(_start_error_message(exc, stage)) from exc

    async def _expire(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            await self.close()
        except asyncio.CancelledError:
            return

    async def poll(self) -> dict[str, Any]:
        """读取页面自行完成的扫码进度；不另外调用 QQ 的轮询接口。"""
        if self._code:
            return {"status": "authorized", "code": self._code}
        if self._closed or not self._page or self._page.is_closed():
            return {
                "status": "expired",
                "message": "QQ 登录会话已结束，请重新获取二维码",
                "terminal": True,
            }
        try:
            texts = await asyncio.gather(
                *(
                    frame.locator("body").inner_text(timeout=1200)
                    for frame in self._page.frames
                ),
                return_exceptions=True,
            )
            text = " ".join(value for value in texts if isinstance(value, str))
        except Exception:
            text = ""
        if re.search(r"二维码.*(?:失效|过期)|二维码已失效", text):
            return {
                "status": "expired",
                "message": "QQ 二维码已过期，请重新获取",
                "terminal": True,
            }
        scanned = bool(re.search(r"扫码成功|请在手机上确认|已扫码", text))
        return {
            "status": "scanned" if scanned else "waiting",
            "message": "已扫码，请在 QQ 中确认" if scanned else "等待 QQ 扫码",
        }

    async def close(self) -> None:
        """成功、取消、过期或异常时释放本会话全部资源；重复调用安全。"""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            if self._expiry_task and self._expiry_task is not asyncio.current_task():
                self._expiry_task.cancel()
            for resource in (self._context, self._browser):
                if resource is not None:
                    try:
                        await resource.close()
                    except Exception:
                        pass
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass


async def exchange_qq_code(http: HttpClient, code: str) -> dict[str, Any]:
    """按照上游 YSDK 协议，将 QQ 授权码换成平台登录凭据。

    Args:
        http: 复用插件的 HTTP 客户端。
        code: 同一浏览器扫码会话取得的 QQ 授权码。

    Returns:
        平台凭据；仅供后端换取营地登录态。

    Raises:
        ValueError: 换票失败或缺少必需字段。
    """
    timestamp = str(int(time.time()))
    body = json.dumps({"appID": QQ_APP_ID, "loginCode": code}, separators=(",", ":"))
    sign_text = f"POST\n/cmd/QQCodeLogin\njson\nysdk\n{timestamp}\n{body}"
    digest = base64.b64encode(
        hmac.new(YSDK_SIGN_KEY, sign_text.encode(), hashlib.sha256).digest()
    ).decode("ascii")
    response = await http.request(
        "POST",
        YSDK_URL,
        headers={
            "Content-Type": "json",
            "Auth-Secret-ID": "ysdk",
            "Auth-Secret-Digest": digest,
            "Auth-Request-Time": timestamp,
        },
        data=body,
    )
    payload = response.json() or {}
    if not isinstance(payload, dict):
        raise ValueError("QQ 授权响应格式异常，请重新扫码")
    data = payload.get("data") if isinstance(payload, dict) else None
    if (
        not response.ok
        or payload.get("code") != 0
        or not isinstance(data, dict)
        or data.get("ret") != 0
    ):
        raise ValueError("QQ 授权换票失败，请重新扫码")
    if not data.get("accessToken") or not data.get("openID"):
        raise ValueError("QQ 授权响应不完整，请重新扫码")
    return data
