"""Эмиссия событий планировщика в единый журнал (log-service).

Сейчас — события санитарного контроля уборки (cleaning_overdue, #265). Сток
устойчив к сбоям log-service: ошибка логируется и не роняет тик планировщика.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

import httpx

from monitoring_shared import Event, EventSource, EventType, Severity
from scheduler.camera_store import CameraInfo
from scheduler.cleaning import OverdueResult

logger = logging.getLogger(__name__)


class EventSink(Protocol):
    """Сток событий (реализуется HTTP-клиентом или фейком в тестах)."""

    def emit(self, event: Event) -> None:
        """Отправить событие в журнал."""
        ...


class HttpEventSink:
    """Сток в log-service по HTTP (POST /events); сбои не пробрасываются."""

    def __init__(self, base_url: str, client: Any | None = None) -> None:
        self._url = base_url.rstrip("/") + "/events"
        self._client = client or httpx.Client(timeout=5.0)

    def emit(self, event: Event) -> None:
        """Отправить событие (ошибки логируются, тик планировщика не падает)."""
        try:
            response = self._client.post(self._url, json=event.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            logger.warning("log-service недоступен, событие потеряно: %s", exc)
            return
        if response.status_code >= 400:
            logger.warning("log-service отклонил событие: %s", response.status_code)


def build_cleaning_overdue(result: OverdueResult, now: datetime) -> Event:
    """Событие «не убрано вовремя» из результата оценки правил.

    source=analytics: контроль построен на данных видеоаналитики покрытия.
    """
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.CLEANING_OVERDUE,
        room_id=result.room_id,
        severity=Severity.WARNING,
        message=result.message,
        payload={"zone": result.zone_type, "reason": result.reason},
    )


def _camera_where(cam: CameraInfo) -> str:
    """Человекочитаемое «где» для текста события о камере."""
    return cam.room_name or cam.room_id or "неизвестном помещении"


def build_camera_offline(cam: CameraInfo, now: datetime) -> Event:
    """Событие «камера не отвечает» (#283).

    source=analytics: живость камеры относится к контуру видеоаналитики.
    """
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.CAMERA_OFFLINE,
        room_id=cam.room_id,
        severity=Severity.WARNING,
        message=f"Камера «{cam.name}» в {_camera_where(cam)} не отвечает",
        payload={"camera_id": cam.id, "camera_name": cam.name},
    )


def build_camera_online(cam: CameraInfo, now: datetime) -> Event:
    """Событие «камера снова на связи» (снятие, #283)."""
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.CAMERA_ONLINE,
        room_id=cam.room_id,
        severity=Severity.INFO,
        message=f"Камера «{cam.name}» в {_camera_where(cam)} снова на связи",
        payload={"camera_id": cam.id, "camera_name": cam.name},
    )


def build_media_gateway_offline(now: datetime) -> Event:
    """Событие «медиа-шлюз go2rtc недоступен» (#286).

    Один агрегированный сигнал вместо лавины `camera_offline` по всем камерам:
    при упавшем шлюзе состояние самих камер неизвестно.
    """
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.MEDIA_GATEWAY_OFFLINE,
        room_id=None,
        severity=Severity.WARNING,
        message="Медиа-шлюз камер (go2rtc) недоступен — состояние камер неизвестно",
        payload={"service": "media-gateway"},
    )


def build_media_gateway_online(now: datetime) -> Event:
    """Событие «медиа-шлюз go2rtc снова на связи» (снятие, #286)."""
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.MEDIA_GATEWAY_ONLINE,
        room_id=None,
        severity=Severity.INFO,
        message="Медиа-шлюз камер (go2rtc) снова на связи",
        payload={"service": "media-gateway"},
    )


def build_service_silent(service: str, silent_for_min: int, now: datetime) -> Event:
    """Событие «сервис замолчал» (нет heartbeat дольше порога, #284).

    source=analytics: это служебная живость нашего контура (не данные датчиков).
    """
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.SERVICE_SILENT,
        room_id=None,
        severity=Severity.WARNING,
        message=f"Сервис «{service}» не отвечает {silent_for_min} мин",
        payload={"service": service, "silent_for_min": silent_for_min},
    )


def build_service_restored(service: str, now: datetime) -> Event:
    """Событие «сервис снова на связи» (снятие, #284)."""
    return Event(
        id=uuid4(),
        ts=now,
        source=EventSource.ANALYTICS,
        type=EventType.SERVICE_RESTORED,
        room_id=None,
        severity=Severity.INFO,
        message=f"Сервис «{service}» снова на связи",
        payload={"service": service},
    )
