"""Отправка событий аналитики в log-service (внутренний REST).

Сток событий — абстракция (Protocol). HttpEventSink шлёт Event на
POST /events log-service; событие может нести ссылку на артефакт
(Event.artifact_id). Для тестов — CollectingEventSink.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from monitoring_shared import Event

logger = logging.getLogger(__name__)


class EventSink(Protocol):
    """Получатель сформированных событий."""

    def emit(self, event: Event) -> None: ...


class HttpEventSink:
    """Сток в log-service по HTTP (POST /events)."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._url = base_url.rstrip("/") + "/events"
        self._client = client or httpx.Client(timeout=5.0)

    def emit(self, event: Event) -> None:
        """Отправить событие в log-service (ошибки логируются, не пробрасываются).

        Недоступность журнала не должна ронять обработку задания видеоанализа.
        """
        try:
            response = self._client.post(self._url, json=event.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            logger.warning("log-service недоступен, событие потеряно: %s", exc)
            return
        if response.status_code >= 400:
            logger.warning("log-service отклонил событие: %s", response.status_code)


class CollectingEventSink:
    """Сток, накапливающий события в памяти (для тестов)."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)
