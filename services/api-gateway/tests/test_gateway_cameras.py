"""Проверка интерфейса настройки видеоаналитики: камеры и ROI-зоны (api-gateway)."""

from __future__ import annotations

from uuid import uuid4

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import cameras, metadata
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


def _seed_camera(engine: Engine) -> str:
    camera_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            cameras.insert().values(
                id=camera_id,
                room_id="room-01",
                name="cam-01",
                rtsp_url="rtsp://cam-01/stream",
                enabled=True,
            )
        )
    return str(camera_id)


def _client(engine: Engine) -> TestClient:
    return TestClient(create_app(settings=_SETTINGS, engine=engine))


# ── Камеры ──


def test_list_and_get_camera() -> None:
    """Камера видна в списке и читается по id."""
    engine = _engine()
    cam_id = _seed_camera(engine)
    client = _client(engine)

    lst = client.get("/api/v1/cameras").json()["data"]
    assert lst["total"] == 1
    assert lst["items"][0]["id"] == cam_id

    one = client.get(f"/api/v1/cameras/{cam_id}").json()["data"]
    assert one["enabled"] is True
    assert one["analytics"] is None


def test_get_camera_missing() -> None:
    """Отсутствующая камера → 404 CAMERA_NOT_FOUND."""
    resp = _client(_engine()).get(f"/api/v1/cameras/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CAMERA_NOT_FOUND"


def test_patch_camera_toggles() -> None:
    """PATCH выключает функцию аналитики и камеру; флаги analytics сливаются."""
    engine = _engine()
    cam_id = _seed_camera(engine)
    client = _client(engine)

    r1 = client.patch(f"/api/v1/cameras/{cam_id}", json={"analytics": {"coverage": False}})
    assert r1.status_code == 200
    assert r1.json()["data"]["analytics"] == {"coverage": False}

    # Частичное обновление сливается, а не затирает.
    r2 = client.patch(f"/api/v1/cameras/{cam_id}", json={"analytics": {"uniform": False}})
    assert r2.json()["data"]["analytics"] == {"coverage": False, "uniform": False}

    r3 = client.patch(f"/api/v1/cameras/{cam_id}", json={"enabled": False})
    assert r3.json()["data"]["enabled"] is False


def test_patch_camera_unknown_feature_rejected() -> None:
    """Неизвестная функция аналитики → 422 VALIDATION_ERROR."""
    engine = _engine()
    cam_id = _seed_camera(engine)
    resp = _client(engine).patch(f"/api/v1/cameras/{cam_id}", json={"analytics": {"nope": True}})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ── ROI-зоны ──


def test_zone_crud_roundtrip() -> None:
    """Зона создаётся, читается в списке, изменяется и удаляется."""
    engine = _engine()
    cam_id = _seed_camera(engine)
    client = _client(engine)

    assert client.get(f"/api/v1/cameras/{cam_id}/zones").json()["data"]["total"] == 0

    created = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={"zone_type": "table", "polygon": [[0, 0], [0.5, 0], [0.5, 0.5]], "note": "стол"},
    ).json()["data"]
    assert created["zone_type"] == "table"
    zone_id = created["id"]

    assert client.get(f"/api/v1/cameras/{cam_id}/zones").json()["data"]["total"] == 1

    patched = client.patch(f"/api/v1/zones/{zone_id}", json={"zone_type": "floor"}).json()["data"]
    assert patched["zone_type"] == "floor"

    assert client.delete(f"/api/v1/zones/{zone_id}").status_code == 200
    assert client.get(f"/api/v1/cameras/{cam_id}/zones").json()["data"]["total"] == 0


def test_zone_invalid_polygon_rejected() -> None:
    """Полигон с <3 вершин или координатами вне [0,1] → 422."""
    engine = _engine()
    cam_id = _seed_camera(engine)
    client = _client(engine)

    too_few = client.post(
        f"/api/v1/cameras/{cam_id}/zones", json={"zone_type": "table", "polygon": [[0, 0], [1, 1]]}
    )
    assert too_few.status_code == 422

    out_of_range = client.post(
        f"/api/v1/cameras/{cam_id}/zones",
        json={"zone_type": "table", "polygon": [[0, 0], [0, 1], [1, 2]]},
    )
    assert out_of_range.status_code == 422


def test_zone_for_missing_camera() -> None:
    """Зона для несуществующей камеры → 404 CAMERA_NOT_FOUND."""
    resp = _client(_engine()).post(
        f"/api/v1/cameras/{uuid4()}/zones",
        json={"zone_type": "table", "polygon": [[0, 0], [0.5, 0], [0.5, 0.5]]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CAMERA_NOT_FOUND"


def test_patch_and_delete_missing_zone() -> None:
    """Изменение/удаление несуществующей зоны → 404 ZONE_NOT_FOUND."""
    client = _client(_engine())
    assert client.patch("/api/v1/zones/999", json={"zone_type": "floor"}).status_code == 404
    resp = client.delete("/api/v1/zones/999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ZONE_NOT_FOUND"
