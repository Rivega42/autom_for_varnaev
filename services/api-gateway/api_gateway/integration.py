"""Разъёмы АУРА (/integration/*) — заглушены за фичефлагом (docs/03_API_CONTRACT.md §4).

# СТЫК-АУРА (v2): эти эндпойнты существуют, но при выключенной интеграции
возвращают 501 NOT_IMPLEMENTED. Включение — фичефлагом `AURA_INTEGRATION_ENABLED`
или тумблером в GUI (хранится в app_config, приоритетнее env), без дописывания
кода (CLAUDE.md §4). Пути стабильны с v1.

Реализованные разъёмы (отвечают по контракту при включённой интеграции):
- D.1 `POST /integration/analysis-tasks` — АУРА ставит задание на анализ (#348).
- D.3 `GET /integration/events` — АУРА читает события за период (#347).
Остальные (D.4) пока заглушены до своих задач.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.params import Depends
from pydantic import ValidationError
from sqlalchemy import Engine

from api_gateway.errors import api_error
from api_gateway.events_client import EventsClient
from api_gateway.query_params import parse_query_dt
from api_gateway.schemas import AnalysisTaskCreate
from api_gateway.tasks_repository import create_task
from monitoring_shared import ErrorCode, TaskTrigger, ok

INTEGRATION_PREFIX = "/api/v1/integration"


def require_aura_enabled(enabled: bool) -> None:
    """Пропустить запрос только если интеграция включена, иначе 501.

    `enabled` — действующее значение флага (из БД/env, вычисляется на момент
    запроса), поэтому тумблер в GUI применяется без перезапуска сервиса.
    """
    if not enabled:
        raise api_error(ErrorCode.NOT_IMPLEMENTED, "Интеграция с АУРА отключена")


def _not_implemented_in_v2() -> dict[str, Any]:
    """Разъём включён, но его v2-логика ещё не реализована → 501."""
    # СТЫК-АУРА (v2): здесь появится реальная обработка запроса от АУРА.
    raise api_error(ErrorCode.NOT_IMPLEMENTED, "Разъём АУРА ещё не реализован")


def register_integration_routes(
    app: FastAPI,
    engine: Engine,
    events: EventsClient,
    aura_enabled: Callable[[], bool],
    dependencies: Sequence[Depends] | None = None,
) -> None:
    """Зарегистрировать разъёмы АУРА на приложении.

    `engine` — БД (создание заданий D.1); `events` — источник событий (D.3, тот
    же, что у публичных эндпойнтов журнала). `aura_enabled` — функция,
    возвращающая действующее значение фичефлага на момент запроса (БД-тумблер
    приоритетнее env), чтобы включение/выключение из GUI применялось без
    перезапуска. `dependencies` (например, проверка X-API-Key) — ко всем разъёмам.
    """
    deps = list(dependencies) if dependencies else None

    @app.post(f"{INTEGRATION_PREFIX}/analysis-tasks", dependencies=deps)
    async def integration_post_task(request: Request) -> dict[str, Any]:
        """§4.1 (D.1) АУРА ставит задание на анализ файла. Выкл → 501; вкл → 200.

        АУРА кладёт видеофрагмент на общий том artifacts и шлёт задание; создаём
        его со status=queued, trigger=aura. `callback_url` (если задан) сохраняем
        для уведомления о готовности (D.5).

        Тело читаем и валидируем ВРУЧНУЮ — ПОСЛЕ проверки фичефлага, чтобы
        выключенный разъём отдавал 501 даже на кривое тело (а не 422 от валидатора
        FastAPI, который сработал бы до обработчика). Граница v1 — приоритетнее.
        """
        require_aura_enabled(aura_enabled())  # выкл → 501 ДО разбора тела
        raw = await request.body()
        if not raw.strip():
            raise api_error(ErrorCode.VALIDATION_ERROR, "Тело задания обязательно (D.1)")
        try:
            body = AnalysisTaskCreate.model_validate_json(raw)
        except ValidationError as exc:
            raise api_error(ErrorCode.VALIDATION_ERROR, "Некорректное тело задания (D.1)") from exc
        return ok(create_task(engine, body, trigger=TaskTrigger.AURA))

    @app.get(f"{INTEGRATION_PREFIX}/events", dependencies=deps)
    def integration_get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        """§4.2 (D.3) АУРА читает события за период. Выкл → 501; вкл → 200.

        Наружу отдаём ТОЛЬКО события журнала (не показания датчиков и не видео) —
        тем же источником, что и публичный GET /events. Фильтры from/to/type
        необязательны; даты валидируются до похода в log-service (#205).
        Постраничный забор — `limit`/`offset` (как у публичного эндпойнта): за
        период может быть больше событий, чем `limit`; полное число — в `total`.
        """
        require_aura_enabled(aura_enabled())  # выкл → 501
        parse_query_dt(from_)
        parse_query_dt(to)
        data = events.list_events(
            {"from": from_, "to": to, "type": type, "limit": limit, "offset": offset}
        )
        return ok(data)

    @app.put(f"{INTEGRATION_PREFIX}/settings", dependencies=deps)
    def integration_put_settings() -> dict[str, Any]:
        """§4.3 АУРА передаёт настройки (v2). Выкл → 501."""
        require_aura_enabled(aura_enabled())
        return _not_implemented_in_v2()
