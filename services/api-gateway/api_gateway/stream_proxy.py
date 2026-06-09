"""Прокси MJPEG-видеопотока камеры от go2rtc (живое видео в GUI).

go2rtc отдаёт поток `multipart/x-mixed-replace` по `GET /api/stream.mjpeg?src=<имя>`.
go2rtc — во внутренней сети; поток проксируется наружу через api-gateway (как и
кадр-снимок), чтобы не публиковать go2rtc. Источник абстрагирован Protocol'ом
для подмены в тестах.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import httpx


class StreamProxy(Protocol):
    """Источник MJPEG-потока по имени потока (для подмены в тестах)."""

    async def open(self, src: str) -> tuple[str, AsyncIterator[bytes]] | None:
        """Открыть поток `src`: вернуть (media_type, асинхронный итератор байт) или None."""
        ...


class Go2rtcStreamProxy:
    """Боевой источник: ретранслирует MJPEG-поток go2rtc."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    async def open(self, src: str) -> tuple[str, AsyncIterator[bytes]] | None:
        """Открыть MJPEG-поток go2rtc; None — если go2rtc недоступен/ответил не 200.

        Клиент и ответ держатся открытыми, пока итератор отдаёт байты, и
        закрываются в `finally` (в т.ч. при разрыве со стороны браузера).
        """
        client = httpx.AsyncClient(timeout=None)
        url = f"{self._base}/api/stream.mjpeg"
        try:
            request = client.build_request("GET", url, params={"src": src})
            response = await client.send(request, stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return None
        if response.status_code != 200:
            await response.aclose()
            await client.aclose()
            return None
        media_type = response.headers.get("content-type", "multipart/x-mixed-replace")

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return media_type, body()
