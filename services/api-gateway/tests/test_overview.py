"""Тесты обзорного агрегата (#288): живость узлов/камер, алерты, последние данные."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.overview_repository import build_overview
from api_gateway.tables import cameras, metadata, rooms, sensor_nodes, sensor_readings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)

_SETTINGS = Settings(
    log_service_url="http://log-service:8000", api_key=None, aura_integration_enabled=False
)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine


def _seed(engine: Engine, cam_id: object) -> None:
    with engine.begin() as conn:
        conn.execute(rooms.insert().values(id="room-01", name="Цех", is_cold=False))
        conn.execute(
            sensor_nodes.insert().values(id="node-01", room_id="room-01", placement="стена")
        )
        conn.execute(
            sensor_nodes.insert().values(id="node-02", room_id="room-01", placement="потолок")
        )
        conn.execute(
            cameras.insert().values(
                id=cam_id, room_id="room-01", name="Кухня-1", rtsp_url="rtsp://x", enabled=True
            )
        )
        # свежее показание node-01 (online) и старое node-02 (offline)
        conn.execute(
            sensor_readings.insert().values(
                ts=NOW - timedelta(minutes=2),
                node_id="node-01",
                room_id="room-01",
                metric="air_temp",
                value=5.0,
                unit="C",
            )
        )
        conn.execute(
            sensor_readings.insert().values(
                ts=NOW - timedelta(minutes=40),
                node_id="node-02",
                room_id="room-01",
                metric="humidity",
                value=55.0,
                unit="%",
            )
        )


class _FakeEvents:
    """Фейковый источник событий (полная сигнатура EventsClient для типов)."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"items": self._items, "total": len(self._items)}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        return None

    def create_event(self, event: object) -> None:
        pass

    def ack_event(self, event_id: UUID) -> bool:
        return False


def test_build_overview_aggregates_state() -> None:
    """Узлы по свежести, камера по событию, алерты и последние показания."""
    engine = _engine()
    cam_id = uuid4()
    _seed(engine, cam_id)
    events: list[dict[str, Any]] = [
        {
            "id": str(uuid4()),
            "ts": "2026-06-10T11:50:00Z",
            "type": "camera_offline",
            "severity": "warning",
            "payload": {"camera_id": str(cam_id)},
            "acknowledged_at": None,
        },
        {
            "id": str(uuid4()),
            "ts": "2026-06-10T11:30:00Z",
            "type": "threshold_exceeded",
            "severity": "critical",
            "payload": {},
            "acknowledged_at": None,
        },
        {
            "id": str(uuid4()),
            "ts": "2026-06-10T11:20:00Z",
            "type": "threshold_exceeded",
            "severity": "warning",
            "payload": {},
            "acknowledged_at": "2026-06-10T11:25:00Z",  # подтверждено — не алерт
        },
    ]
    data = build_overview(engine, _FakeEvents(events), NOW, node_silent_min=10)

    # узлы: node-01 свежий → online, node-02 устаревший → offline
    by_node = {n["id"]: n["online"] for n in data["nodes"]}
    assert by_node == {"node-01": True, "node-02": False}

    # камера: последнее событие camera_offline → offline
    assert data["cameras"][0]["online"] is False

    # активные алерты: warning(offline) + critical, подтверждённый warning не в счёт
    assert data["active_alerts"] == 2

    # помещение: последние показания по метрикам
    metrics = data["rooms"][0]["metrics"]
    assert metrics["air_temp"]["value"] == 5.0
    assert metrics["humidity"]["unit"] == "%"

    # лента событий — по убыванию времени, ограничена
    assert data["recent_events"][0]["type"] == "camera_offline"


def test_camera_online_when_no_events() -> None:
    """Без событий живости камера считается на связи (online=True)."""
    engine = _engine()
    cam_id = uuid4()
    _seed(engine, cam_id)
    data = build_overview(engine, _FakeEvents([]), NOW)
    assert data["cameras"][0]["online"] is True
    assert data["active_alerts"] == 0


def test_camera_back_online_after_recovery() -> None:
    """Если последнее событие камеры — camera_online, она снова на связи."""
    engine = _engine()
    cam_id = uuid4()
    _seed(engine, cam_id)
    events: list[dict[str, Any]] = [
        {  # новее → побеждает
            "id": str(uuid4()),
            "ts": "2026-06-10T11:55:00Z",
            "type": "camera_online",
            "severity": "info",
            "payload": {"camera_id": str(cam_id)},
            "acknowledged_at": None,
        },
        {  # старее
            "id": str(uuid4()),
            "ts": "2026-06-10T11:50:00Z",
            "type": "camera_offline",
            "severity": "warning",
            "payload": {"camera_id": str(cam_id)},
            "acknowledged_at": None,
        },
    ]
    data = build_overview(engine, _FakeEvents(events), NOW)
    assert data["cameras"][0]["online"] is True


def test_recent_events_truncated_to_limit() -> None:
    """Лента событий ограничена recent_limit, отсортирована по убыванию времени."""
    engine = _engine()
    _seed(engine, uuid4())
    events: list[dict[str, Any]] = [
        {
            "id": str(uuid4()),
            "ts": f"2026-06-10T10:{m:02d}:00Z",
            "type": "threshold_exceeded",
            "severity": "info",
            "payload": {},
            "acknowledged_at": None,
        }
        for m in range(30)
    ]
    data = build_overview(engine, _FakeEvents(events), NOW, recent_limit=20)
    assert len(data["recent_events"]) == 20
    # первым идёт самое свежее (10:29)
    assert data["recent_events"][0]["ts"] == "2026-06-10T10:29:00Z"


def test_overview_endpoint_wraps_envelope() -> None:
    """GET /overview отдаёт конверт ok с ключами обзора."""
    engine = _engine()
    _seed(engine, uuid4())
    client = TestClient(
        create_app(settings=_SETTINGS, engine=engine, events_client=_FakeEvents([]))
    )
    resp = client.get("/api/v1/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    for key in ("rooms", "nodes", "cameras", "recent_events", "active_alerts"):
        assert key in body["data"]
