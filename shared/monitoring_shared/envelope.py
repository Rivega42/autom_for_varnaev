"""Единый конверт ответа API (docs/03_API_CONTRACT.md §1.1–§1.2).

Один формат успеха/ошибки для всех ответов `api-gateway` (и потенциально других
сервисов). Хелперы `ok()`/`error()` возвращают готовый словарь-конверт; модели
`Envelope`/`ErrorBody` описывают его форму для типизации и OpenAPI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class ErrorCode(StrEnum):
    """Стартовый набор кодов ошибок контракта (docs/03_API_CONTRACT.md §1.2)."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    CAMERA_NOT_FOUND = "CAMERA_NOT_FOUND"
    ZONE_NOT_FOUND = "ZONE_NOT_FOUND"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL = "INTERNAL"


# Сопоставление кода ошибки с HTTP-статусом (см. таблицу §1.2).
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.TASK_NOT_FOUND: 404,
    ErrorCode.EVENT_NOT_FOUND: 404,
    ErrorCode.CAMERA_NOT_FOUND: 404,
    ErrorCode.ZONE_NOT_FOUND: 404,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.INTERNAL: 500,
}


class ErrorBody(BaseModel):
    """Тело ошибки в конверте."""

    code: str
    message: str


class Envelope(BaseModel):
    """Единый конверт ответа: status + data | error + ts."""

    status: Literal["ok", "error"]
    data: Any | None = None
    error: ErrorBody | None = None
    ts: datetime


def _now_iso() -> str:
    """Текущее время UTC в ISO-8601 с суффиксом Z (формат контракта §1)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ok(data: Any) -> dict[str, Any]:
    """Успешный конверт с полезной нагрузкой."""
    return {"status": "ok", "data": data, "error": None, "ts": _now_iso()}


def error(code: str, message: str) -> dict[str, Any]:
    """Конверт-ошибка с кодом и сообщением для оператора."""
    return {
        "status": "error",
        "data": None,
        "error": {"code": str(code), "message": message},
        "ts": _now_iso(),
    }
