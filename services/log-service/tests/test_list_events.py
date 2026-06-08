"""Проверка чтения ленты событий с фильтрами."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app
from log_service.repository import insert_event
from sqlalchemy import Engine

from monitoring_shared import Event, EventSource, EventType, Severity


def _event(type_: EventType, room: str, minute: int) -> Event:
    return Event(
        id=uuid4(),
        ts=datetime(2026, 6, 5, 10, minute, tzinfo=UTC),
        source=EventSource.SENSORS,
        type=type_,
        room_id=room,
        severity=Severity.WARNING,
        message=f"событие {type_.value} в {room}",
        payload={},
    )


def _seed(engine: Engine) -> None:
    insert_event(engine, _event(EventType.THRESHOLD_EXCEEDED, "room-01", 0))
    insert_event(engine, _event(EventType.BACK_TO_NORMAL, "room-01", 5))
    insert_event(engine, _event(EventType.THRESHOLD_EXCEEDED, "room-02", 10))


def test_list_all(engine: Engine) -> None:
    _seed(engine)
    client = TestClient(create_app(engine))
    body = client.get("/events").json()
    assert body["status"] == "ok"
    assert body["data"]["total"] == 3
    # сортировка по убыванию ts — первым самое свежее (minute=10)
    assert body["data"]["items"][0]["room"] == "room-02"


def test_filter_by_type(engine: Engine) -> None:
    _seed(engine)
    client = TestClient(create_app(engine))
    body = client.get("/events", params={"type": "back_to_normal"}).json()
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["type"] == "back_to_normal"


def test_filter_by_room(engine: Engine) -> None:
    _seed(engine)
    client = TestClient(create_app(engine))
    body = client.get("/events", params={"room": "room-01"}).json()
    assert body["data"]["total"] == 2


def test_invalid_date_returns_422(engine: Engine) -> None:
    """Некорректная дата в query log-service → 422 VALIDATION_ERROR (не 500)."""
    client = TestClient(create_app(engine))
    resp = client.get("/events", params={"from": "not-a-date"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
