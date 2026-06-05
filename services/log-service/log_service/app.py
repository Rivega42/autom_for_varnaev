"""FastAPI-приложение log-service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine

from log_service.db import build_engine
from log_service.envelope import ok
from log_service.repository import insert_event
from monitoring_shared import Event


def create_app(engine: Engine | None = None) -> FastAPI:
    """Создать приложение log-service. Engine можно передать (для тестов)."""
    app = FastAPI(title="log-service")
    engine = engine or build_engine()
    app.state.engine = engine

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
