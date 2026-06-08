"""Интеграционный тест: эмулированное MQTT-сообщение → запись в sensor_readings."""

from ingest_sensors.db import DbReadingWriter
from ingest_sensors.pipeline import make_reading_handler
from ingest_sensors.thresholds import ThresholdMonitor
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from monitoring_shared import Event, EventType, Metric, Severity, Threshold, ThresholdOp


class _CollectingSink:
    """Сток событий в память (для проверки эмиссии)."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


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


def _temp_threshold() -> Threshold:
    """Порог: температура воздуха выше 8°C — превышение (severity=warning)."""
    return Threshold(
        id=1,
        room_id="room-01",
        metric=Metric.AIR_TEMP,
        op=ThresholdOp.GT,
        value=8.0,
        severity=Severity.WARNING,
        silent_min=10,
        enabled=True,
    )


def test_threshold_breach_and_recovery_emit_events() -> None:
    """Превышение порога эмитит THRESHOLD_EXCEEDED, возврат — BACK_TO_NORMAL."""
    engine = _make_engine()
    sink = _CollectingSink()
    handler = make_reading_handler(
        DbReadingWriter(engine),
        {"node-01": "room-01"}.get,
        monitor=ThresholdMonitor([_temp_threshold()]),
        sink=sink,
    )

    handler("monitoring/node-01/air_temp", b'{"value": 9.0, "unit": "C"}')  # выше нормы
    handler("monitoring/node-01/air_temp", b'{"value": 5.0, "unit": "C"}')  # вернулось

    assert [e.type for e in sink.events] == [
        EventType.THRESHOLD_EXCEEDED,
        EventType.BACK_TO_NORMAL,
    ]
    # показания обоих сообщений записаны
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sensor_readings")).scalar() == 2


def test_handler_survives_writer_failure() -> None:
    """Сбой записи в БД логируется, но не пробрасывается (цикл приёма жив)."""

    class _FailingWriter:
        def write(self, reading: object) -> None:
            raise RuntimeError("БД недоступна")

    handler = make_reading_handler(_FailingWriter(), {"node-01": "room-01"}.get)
    # Не должно бросить исключение.
    handler("monitoring/node-01/air_temp", b'{"value": 1.0, "unit": "C"}')
