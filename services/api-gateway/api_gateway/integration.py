"""Разъёмы АУРА (/integration/*) — заглушены за фичефлагом (docs/03_API_CONTRACT.md §4).

# СТЫК-АУРА (v2): эти эндпойнты существуют, но при `aura_integration_enabled=false`
возвращают 501 NOT_IMPLEMENTED. Активация — через фичефлаг, без дописывания кода
(CLAUDE.md §4). Пути стабильны с v1.

Реализованные разъёмы (отвечают по контракту при включённом флаге):
- D.3 `GET /integration/events` — АУРА читает события за период (#347).
Остальные (D.1/D.4) пока заглушены до своих задач.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Query
from fastapi.params import Depends

from api_gateway.config import Settings
from api_gateway.errors import api_error
from api_gateway.events_client import EventsClient
from api_gateway.query_params import parse_query_dt
from monitoring_shared import ErrorCode, ok

INTEGRATION_PREFIX = "/api/v1/integration"


def require_aura_enabled(settings: Settings) -> None:
    """Пропустить запрос только если интеграция включена, иначе 501.

    # СТЫК-АУРА (v2): в v1 флаг по умолчанию выключен — разъём заглушён.
    """
    if not settings.aura_integration_enabled:
        raise api_error(ErrorCode.NOT_IMPLEMENTED, "Интеграция с АУРА отключена (v1)")


def _not_implemented_in_v2() -> dict[str, Any]:
    """Разъём включён, но его v2-логика ещё не реализована → 501."""
    # СТЫК-АУРА (v2): здесь появится реальная обработка запроса от АУРА.
    raise api_error(ErrorCode.NOT_IMPLEMENTED, "Разъём АУРА ещё не реализован")


def register_integration_routes(
    app: FastAPI,
    settings: Settings,
    events: EventsClient,
    dependencies: Sequence[Depends] | None = None,
) -> None:
    """Зарегистрировать разъёмы АУРА на приложении.

    `events` — источник событий (тот же, что у публичных эндпойнтов журнала).
    `dependencies` (например, проверка X-API-Key) применяются ко всем разъёмам.
    """
    deps = list(dependencies) if dependencies else None

    @app.post(f"{INTEGRATION_PREFIX}/analysis-tasks", dependencies=deps)
    def integration_post_task() -> dict[str, Any]:
        """§4.1 АУРА ставит задание на анализ файла (v2). v1 → 501."""
        require_aura_enabled(settings)
        return _not_implemented_in_v2()

    @app.get(f"{INTEGRATION_PREFIX}/events", dependencies=deps)
    def integration_get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        """§4.2 (D.3) АУРА читает события за период. v1 → 501; v2 → 200.

        Наружу отдаём ТОЛЬКО события журнала (не показания датчиков и не видео) —
        тем же источником, что и публичный GET /events. Фильтры from/to/type
        необязательны; даты валидируются до похода в log-service (#205).
        Постраничный забор — `limit`/`offset` (как у публичного эндпойнта): за
        период может быть больше событий, чем `limit`; полное число — в `total`.
        """
        require_aura_enabled(settings)  # v1 → 501
        parse_query_dt(from_)
        parse_query_dt(to)
        data = events.list_events(
            {"from": from_, "to": to, "type": type, "limit": limit, "offset": offset}
        )
        return ok(data)

    @app.put(f"{INTEGRATION_PREFIX}/settings", dependencies=deps)
    def integration_put_settings() -> dict[str, Any]:
        """§4.3 АУРА передаёт настройки (v2). v1 → 501."""
        require_aura_enabled(settings)
        return _not_implemented_in_v2()
