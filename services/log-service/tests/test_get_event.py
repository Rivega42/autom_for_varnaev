"""Проверка чтения одного события по id."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app
from log_service.repository import insert_event
from sqlalchemy import Engine

from monitoring_shared import Event, EventSource, EventType, Severity


def _event() -> Event:
    return Event(
        id=uuid4(),
        ts=datetime(2026, 6, 5, 10, 30, tzinfo=UTC),
        source=EventSource.SENSORS,
        type=EventType.THRESHOLD_EXCEEDED,
        room_id="room-01",
        severity=Severity.WARNING,
        message="тест",
        payload={"metric": "air_temp"},
    )


def test_get_existing_event(engine: Engine) -> None:
    """Существующее событие возвращается по id."""
    event = _event()
    insert_event(engine, event)
    client = TestClient(create_app(engine))
    response = client.get(f"/events/{event.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["id"] == str(event.id)


def test_get_missing_event_404(engine: Engine) -> None:
    """Отсутствующее событие → 404 с конвертом EVENT_NOT_FOUND."""
    client = TestClient(create_app(engine))
    response = client.get(f"/events/{uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "EVENT_NOT_FOUND"
