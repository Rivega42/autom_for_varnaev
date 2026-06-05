"""FastAPI-приложение api-gateway: внешний вход контура (docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Query
from sqlalchemy import Engine

from api_gateway.config import Settings
from api_gateway.db import build_engine
from api_gateway.errors import api_error, register_error_handlers
from api_gateway.events_client import EventsClient, HttpEventsClient
from api_gateway.readings_repository import list_readings
from api_gateway.schemas import AnalysisTaskCreate
from api_gateway.tasks_repository import create_task, get_task, list_tasks
from monitoring_shared import ErrorCode, ok

# Базовый префикс контракта (docs/03_API_CONTRACT.md §1).
API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    events_client: EventsClient | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Создать приложение api-gateway.

    `settings`/`events_client`/`engine` можно передать (для тестов); по умолчанию
    берутся из окружения, поднимается HTTP-клиент к log-service и engine БД.
    """
    settings = settings or Settings.from_env()
    events = events_client or HttpEventsClient(settings.log_service_url)
    engine = engine if engine is not None else build_engine()

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

    @app.post(f"{API_PREFIX}/analysis-tasks")
    def post_analysis_task(body: AnalysisTaskCreate) -> dict[str, Any]:
        """Поставить задание на анализ (status=queued, trigger=manual)."""
        return ok(create_task(engine, body))

    @app.get(f"{API_PREFIX}/analysis-tasks")
    def get_analysis_tasks(
        status: str | None = None,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Список заданий с фильтром по статусу/времени."""
        from_ts = datetime.fromisoformat(from_) if from_ else None
        to_ts = datetime.fromisoformat(to) if to else None
        items, total = list_tasks(
            engine,
            status=status,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
        )
        return ok({"items": items, "total": total})

    @app.get(f"{API_PREFIX}/analysis-tasks/{{task_id}}")
    def get_analysis_task(task_id: UUID) -> dict[str, Any]:
        """Статус/результат задания по id или 404 TASK_NOT_FOUND."""
        item = get_task(engine, task_id)
        if item is None:
            raise api_error(ErrorCode.TASK_NOT_FOUND, "Задание не найдено")
        return ok(item)

    @app.get(f"{API_PREFIX}/readings")
    def get_readings(
        room: str | None = None,
        metric: str | None = None,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Показания датчиков (проверочный путь; основной — Grafana)."""
        from_ts = datetime.fromisoformat(from_) if from_ else None
        to_ts = datetime.fromisoformat(to) if to else None
        items = list_readings(
            engine,
            room=room,
            metric=metric,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )
        return ok({"items": items, "total": len(items)})

    return app


app = create_app()
