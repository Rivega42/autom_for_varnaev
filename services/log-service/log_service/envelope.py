"""Единый конверт ответа API (docs/03_API_CONTRACT.md §1.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def ok(data: Any) -> dict[str, Any]:
    """Успешный ответ."""
    return {"status": "ok", "data": data, "error": None, "ts": _now_iso()}


def error(code: str, message: str) -> dict[str, Any]:
    """Ответ-ошибка."""
    return {
        "status": "error",
        "data": None,
        "error": {"code": code, "message": message},
        "ts": _now_iso(),
    }
