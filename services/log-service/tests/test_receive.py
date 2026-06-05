"""Проверка приёма события log-service."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app

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
        payload={"metric": "air_temp", "value": 8.7, "threshold": 8.0},
    )
    return event.model_dump(mode="json")


def test_receive_valid_event() -> None:
    """Валидное событие принимается, возвращается конверт ok с id."""
    client = TestClient(create_app())
    body = _event_json()
    response = client.post("/events", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["id"] == body["id"]
