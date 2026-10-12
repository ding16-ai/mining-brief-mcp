"""统一的 HTTP 访问层：超时、UA、重试、离线开关都在这里收口。"""

from __future__ import annotations

import logging

import httpx

from mining_brief.config import get_settings

logger = logging.getLogger(__name__)


class OfflineMode(RuntimeError):
    """离线模式下禁止任何网络请求。"""


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "User-Agent": settings.user_agent,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    }


def get_text(url: str, *, timeout: float | None = None) -> str:
    """抓取文本资源。失败抛 httpx 异常，由调用方降级。"""
    settings = get_settings()
    if settings.offline:
        raise OfflineMode(f"离线模式已开启，拒绝请求 {url}")

    with httpx.Client(
        timeout=timeout or settings.http_timeout,
        headers=_headers(),
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def get_bytes(url: str, *, timeout: float | None = None) -> bytes:
    settings = get_settings()
    if settings.offline:
        raise OfflineMode(f"离线模式已开启，拒绝请求 {url}")

    with httpx.Client(
        timeout=timeout or settings.http_timeout,
        headers=_headers(),
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def get_json(url: str, *, params: dict | None = None, timeout: float | None = None) -> dict:
    settings = get_settings()
    if settings.offline:
        raise OfflineMode(f"离线模式已开启，拒绝请求 {url}")

    with httpx.Client(
        timeout=timeout or settings.http_timeout,
        headers=_headers(),
        follow_redirects=True,
    ) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()
