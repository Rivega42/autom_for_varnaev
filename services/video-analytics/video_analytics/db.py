"""Подключение video-analytics к БД."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, text

logger = logging.getLogger(__name__)


def database_url() -> str:
    """Собрать URL подключения к БД из окружения."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = quote(os.getenv("POSTGRES_USER", "monitoring"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "monitoring")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def build_engine(url: str | None = None) -> Engine:
    """Создать engine SQLAlchemy."""
    return create_engine(url or database_url())


# UPSERT heartbeat сервиса (watchdog, #284). ON CONFLICT поддерживают PostgreSQL
# и SQLite; имя сервиса — первичный ключ.
_HEARTBEAT = text(
    "INSERT INTO service_heartbeats (service, ts) VALUES (:service, :ts) "
    "ON CONFLICT(service) DO UPDATE SET ts = excluded.ts"
)


def write_heartbeat(engine: Engine, service: str, now: datetime) -> None:
    """Обновить отметку живости сервиса; ошибки логируются, цикл не падает."""
    try:
        with engine.begin() as conn:
            conn.execute(_HEARTBEAT, {"service": service, "ts": now})
    except Exception:
        logger.debug("Не удалось записать heartbeat сервиса %s", service, exc_info=True)
