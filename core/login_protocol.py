"""微信与 QQ 登录共用的营地设备参数和安全负载。"""

from __future__ import annotations

import random
import secrets
import time
from typing import Any

APPID_WX = "wxf4b1e8a3e9aaf978"

CAMP_BASE_URL = "https://ssl.kohsocialapp.qq.com:10001"

WX_QR_URL = "https://open.weixin.qq.com/connect/sdk/qrconnect"

WX_POLL_URL = "https://long.open.weixin.qq.com/connect/l/qrconnect"

COMMON_HEADERS: dict[str, str] = {
    "Content-Encrypt": "",
    "Accept-Encrypt": "",
    "NOENCRYPT": "1",
    "X-Client-Proto": "https",
    "User-Agent": "okhttp/4.9.1",
}

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
