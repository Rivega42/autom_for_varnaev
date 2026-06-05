"""Разъёмы АУРА (/integration/*) — заглушены в v1 (docs/03_API_CONTRACT.md §4).

# СТЫК-АУРА (v2): эти эндпойнты существуют, но пока `aura_integration_enabled=false`
возвращают 501 NOT_IMPLEMENTED. Активация — через фичефлаг, без дописывания кода
(CLAUDE.md §4). Пути стабильны с v1; их реализация появится в v2.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from api_gateway.config import Settings
from api_gateway.errors import api_error
from monitoring_shared import ErrorCode

INTEGRATION_PREFIX = "/api/v1/integration"


def require_aura_enabled(settings: Settings) -> None:
    """Пропустить запрос только если интеграция включена, иначе 501.

    # СТЫК-АУРА (v2): в v1 флаг всегда выключен — разъём заглушён.
    """
    if not settings.aura_integration_enabled:
        raise api_error(ErrorCode.NOT_IMPLEMENTED, "Интеграция с АУРА отключена (v1)")


def _not_implemented_in_v2() -> dict[str, Any]:
    """Разъём включён, но v2-логика ещё не реализована → 501."""
    # СТЫК-АУРА (v2): здесь появится реальная обработка запроса от АУРА.
    raise api_error(ErrorCode.NOT_IMPLEMENTED, "Разъём АУРА ещё не реализован")


def register_integration_routes(app: FastAPI, settings: Settings) -> None:
    """Зарегистрировать заглушённые разъёмы АУРА на приложении."""

    @app.post(f"{INTEGRATION_PREFIX}/analysis-tasks")
    def integration_post_task() -> dict[str, Any]:
        """§4.1 АУРА ставит задание на анализ файла (v2). v1 → 501."""
        require_aura_enabled(settings)
        return _not_implemented_in_v2()

    @app.get(f"{INTEGRATION_PREFIX}/events")
    def integration_get_events() -> dict[str, Any]:
        """§4.2 АУРА читает события (v2). v1 → 501."""
        require_aura_enabled(settings)
        return _not_implemented_in_v2()

    @app.put(f"{INTEGRATION_PREFIX}/settings")
    def integration_put_settings() -> dict[str, Any]:
        """§4.3 АУРА передаёт настройки (v2). v1 → 501."""
        require_aura_enabled(settings)
        return _not_implemented_in_v2()
