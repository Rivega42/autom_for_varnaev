"""Проверка эндпойнта показаний api-gateway (SQLite in-memory)."""

from __future__ import annotations

from datetime import UTC, datetime

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import metadata, sensor_readings
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
    rows = [
        {
            "ts": datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
            "node_id": "node-01",
            "room_id": "room-01",
            "metric": "air_temp",
            "value": 8.7,
            "unit": "C",
        },
        {
            "ts": datetime(2026, 6, 5, 10, 1, tzinfo=UTC),
            "node_id": "node-01",
            "room_id": "room-01",
            "metric": "humidity",
            "value": 55.0,
            "unit": "%",
        },
        {
            "ts": datetime(2026, 6, 5, 10, 2, tzinfo=UTC),
            "node_id": "node-02",
            "room_id": "room-02",
            "metric": "air_temp",
            "value": 21.0,
            "unit": "C",
        },
    ]
    with eng.begin() as conn:
        conn.execute(sensor_readings.insert(), rows)
    return eng


def _client() -> TestClient:
    return TestClient(create_app(settings=_SETTINGS, engine=_engine()))


def test_readings_all() -> None:
    """GET /readings без фильтров → все показания в конверте."""
    resp = _client().get("/api/v1/readings")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3
    assert {"ts", "node_id", "room", "metric", "value", "unit"} <= data["items"][0].keys()


def test_readings_filter_by_room_and_metric() -> None:
    """Фильтры room+metric сужают выборку."""
    resp = _client().get("/api/v1/readings", params={"room": "room-01", "metric": "air_temp"})
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["room"] == "room-01"
    assert data["items"][0]["metric"] == "air_temp"
    assert data["items"][0]["value"] == 8.7


def test_readings_limit() -> None:
    """Параметр limit ограничивает число показаний."""
    resp = _client().get("/api/v1/readings", params={"limit": 1})
    assert resp.json()["data"]["total"] == 1
