"""Проверка приёма и записи события log-service."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app
from sqlalchemy import Engine, text

from monitoring_shared import Event, EventSource, EventType, Severity


def _event_json() -> dict[str, object]:
    event = Event(
        id=uuid4(),
        ts=datetime(2026, 6, 5, 10, 30, tzinfo=UTC),
        source=EventSource.SENSORS,
        type=EventType.THRESHOLD_EXCEEDED,
        room_id="room-01",
        severity=Severity.WARNING,
        message="В холодильной камере температура выше нормы",
        payload={"metric": "air_temp", "value": 8.7},
    )
    return event.model_dump(mode="json")


def test_receive_valid_event_persists(engine: Engine) -> None:
    """Валидное событие принимается и появляется в таблице events."""
    client = TestClient(create_app(engine))
    body = _event_json()
    response = client.post("/events", json=body)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == body["id"]

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, type, message FROM events")).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "threshold_exceeded"
    assert rows[0][2] == "В холодильной камере температура выше нормы"
