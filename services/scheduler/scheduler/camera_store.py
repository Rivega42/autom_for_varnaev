"""Чтение камер из справочника и проба их живости через go2rtc (#283).

Планировщик не пишет в справочник камер — только читает включённые камеры и
проверяет, отдаёт ли каждая видео. Имя потока в go2rtc настраивается равным
имени камеры (`cameras.name`) — так же, как в snapshot api-gateway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import sqlalchemy as sa
from sqlalchemy import Engine

from scheduler.tables import cameras, rooms

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraInfo:
    """Сведения о камере, нужные для проверки живости и текста события."""

    id: str  # UUID в виде строки (для payload и дедупликации эпизодов)
    name: str  # имя потока в go2rtc
    room_id: str | None
    room_name: str | None  # человекочитаемое имя помещения (для оператора)


def load_enabled_cameras(engine: Engine) -> list[CameraInfo]:
    """Загрузить включённые камеры с именем помещения (LEFT JOIN rooms)."""
    stmt = (
        sa.select(cameras.c.id, cameras.c.name, cameras.c.room_id, rooms.c.name.label("room_name"))
        .select_from(cameras.outerjoin(rooms, cameras.c.room_id == rooms.c.id))
        .where(cameras.c.enabled.is_(True))
    )
    with engine.connect() as conn:
        return [
            CameraInfo(
                id=str(row.id),
                name=row.name,
                room_id=row.room_id,
                room_name=row.room_name,
            )
            for row in conn.execute(stmt)
        ]


class CameraProber(Protocol):
    """Проба живости потока по имени (подменяется фейком в тестах)."""

    def is_live(self, stream_name: str) -> bool:
        """True, если go2rtc отдаёт кадр потока (камера на связи)."""
        ...


class Go2rtcCameraProber:
    """Боевая проба: запрашивает у go2rtc один кадр потока.

    Кадр (`GET /api/frame.jpeg?src=<имя>`) приходит только если RTSP-источник
    действительно отдаёт видео — это и есть проверка живости камеры.
    """

    def __init__(self, base_url: str, timeout: float = 5.0, client: Any | None = None) -> None:
        self._url = base_url.rstrip("/") + "/api/frame.jpeg"
        self._timeout = timeout
        self._client = client

    def is_live(self, stream_name: str) -> bool:
        """Вернуть True при 200 с непустым телом; недоступность go2rtc → False."""
        try:
            if self._client is not None:
                resp = self._client.get(self._url, params={"src": stream_name})
            else:
                resp = httpx.get(self._url, params={"src": stream_name}, timeout=self._timeout)
        except httpx.HTTPError as exc:
            logger.debug("Проба камеры %s не удалась: %s", stream_name, exc)
            return False
        return resp.status_code == 200 and bool(resp.content)
