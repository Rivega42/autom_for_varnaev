"""Запись показаний в таблицу sensor_readings."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import Engine, create_engine, text

from monitoring_shared import Reading

logger = logging.getLogger(__name__)

_INSERT = text(
    "INSERT INTO sensor_readings (ts, node_id, room_id, metric, value, unit) "
    "VALUES (:ts, :node_id, :room_id, :metric, :value, :unit)"
)


def reading_params(reading: Reading) -> dict[str, Any]:
    """Преобразовать Reading в параметры INSERT (метрика — строковое значение)."""
    return {
        "ts": reading.ts,
        "node_id": reading.node_id,
        "room_id": reading.room_id,
        "metric": reading.metric.value,
        "value": reading.value,
        "unit": reading.unit,
    }


def _database_url() -> str:
    """Собрать URL подключения к БД из окружения (как в Alembic env.py)."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "monitoring")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "monitoring")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def build_engine(url: str | None = None) -> Engine:
    """Создать engine SQLAlchemy (URL из аргумента или окружения)."""
    return create_engine(url or _database_url())


class DbReadingWriter:
    """Писатель показаний в sensor_readings."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, reading: Reading) -> None:
        """Записать одно показание в БД."""
        with self._engine.begin() as conn:
            conn.execute(_INSERT, reading_params(reading))
