"""FastAPI-приложение log-service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from log_service.db import build_engine
from log_service.envelope import error, ok
from log_service.repository import get_event, insert_event, list_events
from monitoring_shared import Event


def create_app(engine: Engine | None = None) -> FastAPI:
    """Создать приложение log-service. Engine можно передать (для тестов)."""
    app = FastAPI(title="log-service")
    engine = engine or build_engine()
    app.state.engine = engine

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
    def receive_event(event: Event) -> dict[str, Any]:
        """Принять событие и записать его в журнал."""
        insert_event(engine, event)
        return ok({"id": str(event.id)})

    @app.get("/events")
    def get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        room: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Лента событий с фильтрами по времени/типу/помещению."""
        from_ts = datetime.fromisoformat(from_) if from_ else None
        to_ts = datetime.fromisoformat(to) if to else None
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
