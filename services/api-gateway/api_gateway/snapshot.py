"""Получение кадра-превью камеры от go2rtc (фон для разметки ROI в GUI).

go2rtc отдаёт JPEG-кадр по `GET /api/frame.jpeg?src=<имя потока>`. Имя потока в
go2rtc настраивается равным имени камеры (`cameras.name`). go2rtc — во внутренней
сети; кадр проксируется наружу через api-gateway, чтобы не публиковать go2rtc.
"""

from __future__ import annotations

from typing import Protocol

import httpx


class SnapshotFetcher(Protocol):
    """Источник кадра-превью по имени потока (для подмены в тестах)."""

    def fetch(self, src: str) -> bytes | None: ...


class Go2rtcSnapshotFetcher:
    """Боевой источник: тянет JPEG-кадр у go2rtc."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def fetch(self, src: str) -> bytes | None:
        """Вернуть JPEG-кадр потока `src` или None, если go2rtc недоступен."""
        url = f"{self._base}/api/frame.jpeg"
        try:
            resp = httpx.get(url, params={"src": src}, timeout=self._timeout)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.content
