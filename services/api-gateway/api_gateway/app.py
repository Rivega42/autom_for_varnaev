"""FastAPI-приложение api-gateway: внешний вход контура (docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from monitoring_shared import ok

# Базовый префикс контракта (docs/03_API_CONTRACT.md §1).
API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    """Создать приложение api-gateway."""
    app = FastAPI(title="api-gateway")

    @app.get(f"{API_PREFIX}/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса (конверт ok)."""
        return ok({"service": "api-gateway", "up": True})

    return app


app = create_app()
