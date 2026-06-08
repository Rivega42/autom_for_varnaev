"""CRUD порогов и расписаний через api-gateway (настройка из интерфейса)."""

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


# ── Справочники: помещения и узлы датчиков ──


def test_room_crud() -> None:
    """Создание и список помещений; занятый id → 409."""
    client = _client()
    created = client.post(
        "/api/v1/rooms", json={"id": "room-01", "name": "Кухня", "is_cold": False}
    )
    assert created.status_code == 200
    assert created.json()["data"]["id"] == "room-01"
    assert client.get("/api/v1/rooms").json()["data"]["total"] == 1

    # Повторный id → 409.
    dup = client.post("/api/v1/rooms", json={"id": "room-01", "name": "Другая"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ROOM_ALREADY_EXISTS"


def test_sensor_node_crud_and_room_fk() -> None:
    """Узел требует существующего помещения; занятый id → 409."""
    client = _client()
    # Помещения ещё нет → 404 ROOM_NOT_FOUND.
    no_room = client.post("/api/v1/sensor-nodes", json={"id": "node-01", "room_id": "room-01"})
    assert no_room.status_code == 404
    assert no_room.json()["error"]["code"] == "ROOM_NOT_FOUND"

    client.post("/api/v1/rooms", json={"id": "room-01", "name": "Кухня"})
    created = client.post(
        "/api/v1/sensor-nodes",
        json={"id": "node-01", "room_id": "room-01", "placement": "внутри (I2C)"},
    )
    assert created.status_code == 200
    assert created.json()["data"]["room_id"] == "room-01"
    assert client.get("/api/v1/sensor-nodes").json()["data"]["total"] == 1

    # Повторный id узла → 409.
    dup = client.post("/api/v1/sensor-nodes", json={"id": "node-01", "room_id": "room-01"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "NODE_ALREADY_EXISTS"


# ── Пороги ──


def test_threshold_crud() -> None:
    """Создание, список, изменение и удаление порога."""
    client = _client()
    body = {
        "room": "room-02",
        "metric": "air_temp",
        "op": ">",
        "value": 8.0,
        "severity": "warning",
    }
    created = client.post("/api/v1/thresholds", json=body).json()["data"]
    assert created["metric"] == "air_temp"
    assert created["enabled"] is True
    tid = created["id"]

    assert client.get("/api/v1/thresholds").json()["data"]["total"] == 1

    patched = client.patch(f"/api/v1/thresholds/{tid}", json={"value": 6.0, "enabled": False})
    assert patched.status_code == 200
    assert patched.json()["data"]["value"] == 6.0
    assert patched.json()["data"]["enabled"] is False

    assert client.delete(f"/api/v1/thresholds/{tid}").status_code == 200
    assert client.get("/api/v1/thresholds").json()["data"]["total"] == 0


def test_threshold_missing_returns_404() -> None:
    """Изменение/удаление несуществующего порога → 404 THRESHOLD_NOT_FOUND."""
    client = _client()
    assert client.patch("/api/v1/thresholds/999", json={"value": 1.0}).status_code == 404
    resp = client.delete("/api/v1/thresholds/999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "THRESHOLD_NOT_FOUND"


def test_threshold_validation() -> None:
    """Неизвестная метрика → 422."""
    resp = _client().post(
        "/api/v1/thresholds", json={"metric": "pressure", "op": ">", "value": 1.0}
    )
    assert resp.status_code == 422


# ── Расписания (таймер) ──


def test_schedule_crud() -> None:
    """Создание, список, изменение и удаление расписания."""
    client = _client()
    body = {
        "name": "кухня-каждые-15",
        "source_ref": "rtsp://camera.local/stream",
        "room": "room-01",
        "interval_min": 15,
    }
    created = client.post("/api/v1/schedules", json=body).json()["data"]
    assert created["interval_min"] == 15
    assert created["pipeline"] == "pose_v1"
    sid = created["id"]

    assert client.get("/api/v1/schedules").json()["data"]["total"] == 1

    patched = client.patch(f"/api/v1/schedules/{sid}", json={"interval_min": 30})
    assert patched.json()["data"]["interval_min"] == 30

    assert client.delete(f"/api/v1/schedules/{sid}").status_code == 200
    assert client.get("/api/v1/schedules").json()["data"]["total"] == 0


def test_schedule_missing_returns_404() -> None:
    """Несуществующее расписание → 404 SCHEDULE_NOT_FOUND."""
    resp = _client().delete("/api/v1/schedules/999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SCHEDULE_NOT_FOUND"


def test_schedule_validation() -> None:
    """Нулевой интервал → 422."""
    resp = _client().post(
        "/api/v1/schedules",
        json={"name": "x", "source_ref": "rtsp://x", "interval_min": 0},
    )
    assert resp.status_code == 422


def test_schedule_duplicate_name_returns_409() -> None:
    """Создание расписания с уже занятым именем → 409 SCHEDULE_DUPLICATE_NAME."""
    client = _client()
    body = {"name": "повтор", "source_ref": "rtsp://x", "interval_min": 15}
    assert client.post("/api/v1/schedules", json=body).status_code == 200
    resp = client.post("/api/v1/schedules", json=body)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SCHEDULE_DUPLICATE_NAME"


def test_schedule_rename_to_existing_returns_409() -> None:
    """Переименование расписания в уже занятое имя → 409."""
    client = _client()
    client.post(
        "/api/v1/schedules", json={"name": "a", "source_ref": "rtsp://a", "interval_min": 5}
    )
    second = client.post(
        "/api/v1/schedules", json={"name": "b", "source_ref": "rtsp://b", "interval_min": 5}
    ).json()["data"]
    resp = client.patch(f"/api/v1/schedules/{second['id']}", json={"name": "a"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SCHEDULE_DUPLICATE_NAME"
