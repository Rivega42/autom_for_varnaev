"""FastAPI-приложение api-gateway: внешний вход контура (docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Query

from api_gateway.config import Settings
from api_gateway.errors import api_error, register_error_handlers
from api_gateway.events_client import EventsClient, HttpEventsClient
from monitoring_shared import ErrorCode, ok

# Базовый префикс контракта (docs/03_API_CONTRACT.md §1).
API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    events_client: EventsClient | None = None,
) -> FastAPI:
    """Создать приложение api-gateway.

    `settings`/`events_client` можно передать (для тестов); по умолчанию берутся
    из окружения и поднимается HTTP-клиент к log-service.
    """
    settings = settings or Settings.from_env()
    events = events_client or HttpEventsClient(settings.log_service_url)

    app = FastAPI(title="api-gateway")
    register_error_handlers(app)

    @app.get(f"{API_PREFIX}/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса (конверт ok)."""
        return ok({"service": "api-gateway", "up": True})

    @app.get(f"{API_PREFIX}/events")
    def get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        room: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Лента событий журнала (проксируется к log-service)."""
        data = events.list_events(
            {
                "from": from_,
                "to": to,
                "type": type,
                "room": room,
                "limit": limit,
                "offset": offset,
            }
        )
        return ok(data)

    @app.get(f"{API_PREFIX}/events/{{event_id}}")
    def get_event(event_id: UUID) -> dict[str, Any]:
        """Одно событие по id или 404 EVENT_NOT_FOUND."""
        item = events.get_event(event_id)
        if item is None:
            raise api_error(ErrorCode.EVENT_NOT_FOUND, "Событие не найдено")
        return ok(item)

    return app


app = create_app()
