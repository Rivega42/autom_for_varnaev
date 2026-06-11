"""CRUD правил контроля присутствия через api-gateway (#300, #312)."""

from __future__ import annotations

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import metadata
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key=None,
    aura_integration_enabled=False,
)


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _client() -> TestClient:
    return TestClient(create_app(settings=_SETTINGS, engine=_engine()))


def _add_room(client: TestClient, room_id: str = "room-01") -> None:
    client.post("/api/v1/rooms", json={"id": room_id, "name": "Цех"})


def test_presence_rule_crud() -> None:
    """Создание, список, изменение и удаление правила присутствия."""
    client = _client()
    _add_room(client)
    created = client.post(
        "/api/v1/presence-rules",
        json={
            "room": "room-01",
            "window_start": "08:00",
            "window_end": "17:00",
            "max_absence_min": 45,
        },
    )
    assert created.status_code == 200
    rule = created.json()["data"]
    assert rule["window_start"] == "08:00"
    assert rule["window_end"] == "17:00"
    assert rule["max_absence_min"] == 45
    assert rule["enabled"] is True

    listed = client.get("/api/v1/presence-rules").json()["data"]
    assert listed["total"] == 1

    patched = client.patch(
        f"/api/v1/presence-rules/{rule['id']}", json={"max_absence_min": 15, "enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["max_absence_min"] == 15
    assert patched.json()["data"]["enabled"] is False

    deleted = client.delete(f"/api/v1/presence-rules/{rule['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/v1/presence-rules").json()["data"]["total"] == 0


def test_presence_rule_duplicate_window_409_but_second_window_ok() -> None:
    """Дубль окна → 409; другое окно того же помещения — допустимо (смены)."""
    client = _client()
    _add_room(client)
    body = {"room": "room-01", "window_start": "08:00", "window_end": "12:00"}
    assert client.post("/api/v1/presence-rules", json=body).status_code == 200
    dup = client.post("/api/v1/presence-rules", json=body)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "PRESENCE_RULE_DUPLICATE"
    evening = {"room": "room-01", "window_start": "13:00", "window_end": "17:00"}
    assert client.post("/api/v1/presence-rules", json=evening).status_code == 200


def test_presence_rule_unknown_room_404() -> None:
    """Правило для несуществующего помещения → 404 ROOM_NOT_FOUND (не ложный 409)."""
    client = _client()
    resp = client.post(
        "/api/v1/presence-rules",
        json={"room": "ghost", "window_start": "08:00", "window_end": "17:00"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ROOM_NOT_FOUND"


def test_presence_rule_validation_and_404() -> None:
    """Невалидное окно/порог → 422; несуществующее правило → 404."""
    client = _client()
    _add_room(client, "r")
    inverted = client.post(
        "/api/v1/presence-rules",
        json={"room": "r", "window_start": "17:00", "window_end": "08:00"},
    )
    assert inverted.status_code == 422
    empty = client.post(
        "/api/v1/presence-rules",
        json={"room": "r", "window_start": "08:00", "window_end": "08:00"},
    )
    assert empty.status_code == 422
    neg = client.post(
        "/api/v1/presence-rules",
        json={"room": "r", "window_start": "08:00", "window_end": "17:00", "max_absence_min": 0},
    )
    assert neg.status_code == 422
    missing = client.patch("/api/v1/presence-rules/999", json={"enabled": True})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PRESENCE_RULE_NOT_FOUND"
