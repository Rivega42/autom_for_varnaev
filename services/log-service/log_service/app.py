"""FastAPI-приложение log-service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from log_service.db import build_engine


def create_app() -> FastAPI:
    """Создать приложение log-service (engine кладётся в app.state)."""
    app = FastAPI(title="log-service")
    app.state.engine = build_engine()

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса (формат — единый конверт ответа)."""
        return {
            "status": "ok",
            "data": {"service": "log-service", "up": True},
            "error": None,
            "ts": datetime.now(UTC).isoformat(),
        }

    return app


app = create_app()
