"""Клиент к log-service для чтения событий (проксирование).

`api-gateway` не хранит события сам — он обращается к внутреннему `log-service`
(единый журнал). Абстракция `EventsClient` позволяет подменять реализацию в
тестах; рабочая `HttpEventsClient` ходит по REST через httpx.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import httpx

from monitoring_shared import Event


class EventsClient(Protocol):
    """Источник событий для шлюза (реализуется HTTP-клиентом или фейком)."""

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        """Вернуть полезную нагрузку списка событий (`{items, total}`)."""
        ...

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        """Вернуть одно событие или None, если его нет."""
        ...

    def create_event(self, event: Event) -> None:
        """Записать событие в журнал (POST /events log-service)."""
        ...

    def ack_event(self, event_id: UUID) -> bool:
        """Подтвердить событие (#264); False — события нет."""
        ...


def _unwrap(payload: dict[str, Any]) -> Any:
    """Достать `data` из конверта log-service."""
    return payload.get("data")


class HttpEventsClient:
    """Реализация EventsClient поверх REST log-service."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /events?... → распакованная нагрузка `{items, total}`."""
        # Пустые фильтры не передаём, чтобы не засорять запрос.
        query = {k: v for k, v in params.items() if v is not None}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self._base_url}/events", params=query)
        resp.raise_for_status()
        data = _unwrap(resp.json())
        return data if isinstance(data, dict) else {"items": [], "total": 0}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        """GET /events/{id} → событие или None при 404."""
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self._base_url}/events/{event_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = _unwrap(resp.json())
        return data if isinstance(data, dict) else None

    def create_event(self, event: Event) -> None:
        """POST /events log-service — записать событие в единый журнал."""
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base_url}/events", json=event.model_dump(mode="json"))
        resp.raise_for_status()

    def ack_event(self, event_id: UUID) -> bool:
        """POST /events/{id}/ack — подтвердить событие; False при 404."""
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(f"{self._base_url}/events/{event_id}/ack")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True
