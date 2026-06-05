"""FastAPI-приложение log-service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from log_service.db import build_engine
from log_service.envelope import ok
from monitoring_shared import Event


def create_app() -> FastAPI:
    """Создать приложение log-service (engine кладётся в app.state)."""
    app = FastAPI(title="log-service")
    app.state.engine = build_engine()

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса."""
        return ok({"service": "log-service", "up": True})

    @app.post("/events")
    def receive_event(event: Event) -> dict[str, Any]:
        """Принять событие от ingest-sensors/video-analytics.

        Валидация типов/полей выполняется моделью Event (Pydantic). Запись в БД
        добавляется в E3.3; пока возвращаем подтверждение с id события.
        """
        return ok({"id": str(event.id)})

    return app


app = create_app()
