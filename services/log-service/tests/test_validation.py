"""Проверка валидации типов событий при приёме."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app
from sqlalchemy import Engine


def _base_event() -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "ts": datetime(2026, 6, 5, 10, 30, tzinfo=UTC).isoformat(),
        "source": "sensors",
        "type": "threshold_exceeded",
        "room_id": "room-01",
        "severity": "warning",
        "message": "тест",
        "payload": {"metric": "air_temp"},
    }


def test_unknown_type_rejected(engine: Engine) -> None:
    """Неизвестный type → 422 с конвертом ошибки VALIDATION_ERROR."""
    client = TestClient(create_app(engine))
    bad = _base_event()
    bad["type"] = "nonexistent_type"
    response = client.post("/events", json=bad)
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_source_rejected(engine: Engine) -> None:
    """Неизвестный source → 422."""
    client = TestClient(create_app(engine))
    bad = _base_event()
    bad["source"] = "aura"
    response = client.post("/events", json=bad)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_missing_message_rejected(engine: Engine) -> None:
    """Отсутствие обязательного message → 422."""
    client = TestClient(create_app(engine))
    bad = _base_event()
    del bad["message"]
    response = client.post("/events", json=bad)
    assert response.status_code == 422
