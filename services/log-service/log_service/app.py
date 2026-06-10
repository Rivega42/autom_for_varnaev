"""FastAPI-приложение log-service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from log_service.db import build_engine
from log_service.envelope import error, ok
from log_service.notifications import Notifier, build_notifier_from_env
from log_service.repository import get_event, insert_event, list_events
from monitoring_shared import Event


def _as_utc(dt: datetime) -> datetime:
    """Время без зоны трактовать как UTC (контракт), иначе фильтр зависел бы от TZ БД."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def create_app(engine: Engine | None = None, notifier: Notifier | None = None) -> FastAPI:
    """Создать приложение log-service. Engine/notifier можно передать (для тестов)."""
    app = FastAPI(title="log-service")
    engine = engine or build_engine()
    # Диспетчер уведомлений: из окружения по умолчанию (без каналов — отключён).
    notifier = notifier if notifier is not None else build_notifier_from_env()
    app.state.engine = engine
    app.state.notifier = notifier

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        """Ошибки валидации тела (в т.ч. неизвестный source/type) → конверт."""
        return JSONResponse(
            status_code=422,
            content=error("VALIDATION_ERROR", "Тело запроса не прошло валидацию"),
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса."""
        return ok({"service": "log-service", "up": True})

    @app.post("/events")
    def receive_event(event: Event, background: BackgroundTasks) -> dict[str, Any]:
        """Принять событие, записать в журнал и (в фоне) разослать уведомления.

        Рассылка — фоновой задачей ПОСЛЕ ответа: медленный/недоступный канал
        (Telegram/SMTP) не должен задерживать приём событий от ingest/analytics.
        """
        insert_event(engine, event)
        background.add_task(notifier.notify, event)  # best-effort, сбои гасятся внутри
        return ok({"id": str(event.id)})

    @app.get("/events", response_model=None)
    def get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        room: str | None = None,
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any] | JSONResponse:
        """Лента событий с фильтрами по времени/типу/помещению."""
        try:
            from_ts = _as_utc(datetime.fromisoformat(from_)) if from_ else None
            to_ts = _as_utc(datetime.fromisoformat(to)) if to else None
        except ValueError:
            return JSONResponse(
                status_code=422,
                content=error("VALIDATION_ERROR", "Неверный формат даты (ожидается ISO-8601)"),
            )
        items, total = list_events(
            engine,
            from_ts=from_ts,
            to_ts=to_ts,
            type_=type,
            room=room,
            limit=limit,
            offset=offset,
        )
        return ok({"items": items, "total": total})

    @app.get("/events/{event_id}", response_model=None)
    def get_event_by_id(event_id: UUID) -> dict[str, Any] | JSONResponse:
        """Одно событие по id или 404 (EVENT_NOT_FOUND)."""
        item = get_event(engine, event_id)
        if item is None:
            return JSONResponse(
                status_code=404,
                content=error("EVENT_NOT_FOUND", "Событие не найдено"),
            )
        return ok(item)

    return app


app = create_app()
