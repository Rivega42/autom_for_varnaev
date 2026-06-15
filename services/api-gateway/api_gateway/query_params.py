"""Разбор query-параметров шлюза (общий для основных и интеграционных эндпойнтов).

Вынесено из app.py, чтобы разъёмы АУРА (`/integration/*`) валидировали даты тем
же кодом, что и публичные эндпойнты (иначе кривая дата уходит в log-service и
422 превращается в 500 на raise_for_status, см. #205).
"""

from __future__ import annotations

from datetime import UTC, datetime

from api_gateway.errors import api_error
from monitoring_shared import ErrorCode


def parse_query_dt(value: str | None) -> datetime | None:
    """Разобрать ISO-8601 из query-параметра или вернуть 422 VALIDATION_ERROR.

    Время без зоны трактуем как UTC (контракт §1): иначе naive datetime в
    сравнении с timestamptz-колонкой роняет запрос в 500 на стороне БД.
    """
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise api_error(
            ErrorCode.VALIDATION_ERROR, "Неверный формат даты (ожидается ISO-8601)"
        ) from None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
