"""Чтение/запись heartbeat'ов сервисов (#284).

Каждый сервис обновляет свою строку в `service_heartbeats` (UPSERT по имени).
SQL диалект-нейтрален: `ON CONFLICT(service)` поддерживают и PostgreSQL, и SQLite
(в тестах). Планировщик читает все heartbeat'ы и пишет свой.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

# UPSERT строки сервиса: вставить или обновить ts по существующему service (PK).
_UPSERT = text(
    "INSERT INTO service_heartbeats (service, ts) VALUES (:service, :ts) "
    "ON CONFLICT(service) DO UPDATE SET ts = excluded.ts"
)


def write_heartbeat(engine: Engine, service: str, now: datetime) -> None:
    """Обновить heartbeat сервиса; ошибки логируются и не роняют цикл."""
    try:
        with engine.begin() as conn:
            conn.execute(_UPSERT, {"service": service, "ts": now})
    except Exception:
        logger.debug("Не удалось записать heartbeat сервиса %s", service, exc_info=True)


def _coerce_ts(value: object) -> datetime:
    """Привести значение ts к datetime (PostgreSQL отдаёт datetime, SQLite — строку)."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def load_heartbeats(engine: Engine) -> dict[str, datetime]:
    """Вернуть последний heartbeat по каждому сервису ({service: ts})."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT service, ts FROM service_heartbeats"))
        return {row.service: _coerce_ts(row.ts) for row in rows}
