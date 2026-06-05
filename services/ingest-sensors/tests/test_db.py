"""Проверка записи показаний (на in-memory SQLite)."""

from datetime import UTC, datetime

from ingest_sensors.db import DbReadingWriter, reading_params
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from monitoring_shared import Metric, Reading

_READING = Reading(
    ts=datetime(2026, 6, 5, 10, 30, tzinfo=UTC),
    node_id="node-01",
    room_id="room-01",
    metric=Metric.AIR_TEMP,
    value=8.7,
    unit="C",
)


def test_reading_params_mapping() -> None:
    """Параметры INSERT соответствуют полям Reading (метрика — строкой)."""
    params = reading_params(_READING)
    assert params["node_id"] == "node-01"
    assert params["room_id"] == "room-01"
    assert params["metric"] == "air_temp"
    assert params["value"] == 8.7
    assert params["unit"] == "C"


def test_write_reading_inserts_row() -> None:
    """write() реально вставляет строку (проверяем на SQLite)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE sensor_readings "
                "(ts TIMESTAMP, node_id TEXT, room_id TEXT, metric TEXT, value REAL, unit TEXT)"
            )
        )

    DbReadingWriter(engine).write(_READING)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT node_id, metric, value, unit FROM sensor_readings")
        ).fetchall()

    assert len(rows) == 1
    assert rows[0] == ("node-01", "air_temp", 8.7, "C")
