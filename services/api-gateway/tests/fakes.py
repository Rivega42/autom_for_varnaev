"""Общие тест-двойники для проверок api-gateway.

Единый фейк источника событий (`EventsClient`) для тестов событий и разъёмов
АУРА: фиксирует переданные фильтры (`last_params`) и созданные события
(`created`), чтобы тесты могли их проверить. Полнофункциональная версия —
покрывает и сценарии чтения/подтверждения (`get_event`/`ack_event`), и сценарии
заглушек, где достаточно одного `list_events`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


class FakeEventsClient:
    """Фейковый источник событий: фиксирует переданные фильтры и созданные события."""

    def __init__(self, event: dict[str, Any] | None = None) -> None:
        self._event = event
        self.last_params: dict[str, Any] | None = None
        self.created: list[Any] = []

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        self.last_params = params
        items = [self._event] if self._event else []
        return {"items": items, "total": len(items)}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        if self._event and self._event["id"] == str(event_id):
            return self._event
        return None

    def create_event(self, event: object) -> None:
        self.created.append(event)

    def ack_event(self, event_id: UUID) -> bool:
        # подтверждается только «существующее» событие фейка
        return bool(self._event and self._event["id"] == str(event_id))
