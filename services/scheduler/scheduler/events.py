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
