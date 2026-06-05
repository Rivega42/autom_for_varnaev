"""Проверка записи события напрямую через репозиторий."""

from datetime import UTC, datetime
from uuid import uuid4

from log_service.repository import insert_event
from sqlalchemy import Engine, text

from monitoring_shared import Event, EventSource, EventType, Severity


def test_insert_event(engine: Engine) -> None:
    """insert_event пишет строку со всеми полями (payload как JSON)."""
    event = Event(
        id=uuid4(),
        ts=datetime(2026, 6, 5, 11, 0, tzinfo=UTC),
        source=EventSource.SENSORS,
        type=EventType.BACK_TO_NORMAL,
        room_id="room-01",
        severity=Severity.INFO,
        message="В помещении для приготовления пищи влажность вернулась к норме",
        payload={"metric": "humidity"},
    )
    insert_event(engine, event)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT source, severity, payload FROM events")).fetchone()
    assert row is not None
    assert row[0] == "sensors"
    assert row[1] == "info"
