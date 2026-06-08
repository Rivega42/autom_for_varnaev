"""Проверка эндпойнтов заданий на анализ api-gateway (SQLite in-memory)."""

from __future__ import annotations

from uuid import uuid4

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


def _client(engine: Engine) -> TestClient:
    return TestClient(create_app(settings=_SETTINGS, engine=engine))


_BODY = {
    "source_type": "stream",
    "source_ref": "rtsp://cam-01/stream",
    "room": "room-01",
    "pipeline": "pose_v1",
    "params": {"fps": 5},
}


def test_create_task_returns_queued() -> None:
    """POST /analysis-tasks создаёт задание queued/manual и возвращает его."""
    client = _client(_engine())
    resp = client.post("/api/v1/analysis-tasks", json=_BODY)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "queued"
    assert data["trigger"] == "manual"
    assert data["room"] == "room-01"
    assert data["pipeline"] == "pose_v1"
    assert "id" in data


def test_create_task_validation_error() -> None:
    """Невалидное тело (нет source_ref) → 422 VALIDATION_ERROR."""
    client = _client(_engine())
    bad = {k: v for k, v in _BODY.items() if k != "source_ref"}
    resp = client.post("/api/v1/analysis-tasks", json=bad)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_task_with_camera_id() -> None:
    """camera_id из тела сохраняется и возвращается (для применения настроек камеры)."""
    client = _client(_engine())
    cam_id = str(uuid4())
    resp = client.post("/api/v1/analysis-tasks", json={**_BODY, "camera_id": cam_id})
    assert resp.status_code == 200
    assert resp.json()["data"]["camera_id"] == cam_id


def test_get_task_roundtrip() -> None:
    """Созданное задание читается по id."""
    client = _client(_engine())
    created = client.post("/api/v1/analysis-tasks", json=_BODY).json()["data"]
    resp = client.get(f"/api/v1/analysis-tasks/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == created["id"]


def test_get_task_missing() -> None:
    """Отсутствующее задание → 404 TASK_NOT_FOUND."""
    client = _client(_engine())
    resp = client.get(f"/api/v1/analysis-tasks/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_list_tasks_with_status_filter() -> None:
    """Список заданий фильтруется по статусу и возвращает total."""
    engine = _engine()
    client = _client(engine)
    client.post("/api/v1/analysis-tasks", json=_BODY)
    client.post("/api/v1/analysis-tasks", json=_BODY)

    all_resp = client.get("/api/v1/analysis-tasks").json()["data"]
    assert all_resp["total"] == 2
    assert len(all_resp["items"]) == 2

    none_resp = client.get("/api/v1/analysis-tasks", params={"status": "done"}).json()["data"]
    assert none_resp["total"] == 0


def test_invalid_from_date_returns_422() -> None:
    """Некорректная дата в query → 422 VALIDATION_ERROR (не 500)."""
    resp = _client(_engine()).get("/api/v1/analysis-tasks?from=not-a-date")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_envelope_ts_has_z_suffix() -> None:
    """Поле ts конверта оканчивается на Z (формат контракта §1)."""
    resp = _client(_engine()).get("/api/v1/health")
    assert resp.json()["ts"].endswith("Z")
