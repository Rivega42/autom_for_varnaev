"""FastAPI-приложение log-service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from log_service.db import build_engine
from log_service.envelope import error, ok
from log_service.repository import insert_event
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

    return app


app = create_app()
