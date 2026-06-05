"""Интеграционный тест: эмулированное MQTT-сообщение → запись в sensor_readings."""

from ingest_sensors.db import DbReadingWriter
from ingest_sensors.pipeline import make_reading_handler
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool


def _make_engine() -> Engine:
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
    return engine


def test_mqtt_message_results_in_db_row() -> None:
    """Сообщение проходит разбор и попадает в БД с корректными полями."""
    engine = _make_engine()
    handler = make_reading_handler(DbReadingWriter(engine), {"node-01": "room-01"}.get)

    handler("monitoring/node-01/air_temp", b'{"value": 23.4, "unit": "C"}')

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT node_id, room_id, metric, value, unit FROM sensor_readings")
        ).fetchall()
    assert len(rows) == 1
    assert tuple(rows[0]) == ("node-01", "room-01", "air_temp", 23.4, "C")


def test_unknown_node_message_is_skipped() -> None:
    """Сообщение от неизвестного узла не пишется в БД."""
    engine = _make_engine()
    handler = make_reading_handler(DbReadingWriter(engine), {"node-01": "room-01"}.get)

    handler("monitoring/node-99/air_temp", b'{"value": 1.0, "unit": "C"}')

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM sensor_readings")).scalar()
    assert count == 0
