"""Тесты аудита значимых действий (#292): запись, доступ к журналу, фильтр ролей."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from api_gateway.app import create_app
from api_gateway.audit import list_audit, write_audit
from api_gateway.config import Settings
from api_gateway.tables import metadata
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_KEYS = {"opkey": "operator", "adkey": "admin"}
_ROOM = {"id": "room-01", "name": "Цех", "is_cold": False}


class _FakeEvents:
    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"items": [], "total": 0}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        return None

    def create_event(self, event: object) -> None:
        pass

    def ack_event(self, event_id: UUID) -> bool:
        return True


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine


def _client(engine: Engine) -> TestClient:
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=False,
        api_keys=_KEYS,
    )
    return TestClient(create_app(settings=settings, engine=engine, events_client=_FakeEvents()))


# ── Чистые write_audit / list_audit ──


def test_write_and_list_audit() -> None:
    """Запись попадает в журнал и читается (новые сверху)."""
    engine = _engine()
    write_audit(
        engine,
        actor="admin",
        role="admin",
        action="POST",
        target="/x",
        now=datetime(2026, 6, 10, tzinfo=UTC),
    )
    write_audit(
        engine,
        actor="admin",
        role="admin",
        action="DELETE",
        target="/y",
        now=datetime(2026, 6, 11, tzinfo=UTC),
    )
    items = list_audit(engine)
    assert [i["action"] for i in items] == ["DELETE", "POST"]
    assert items[0]["target"] == "/y"


# ── Аудит через эндпойнты ──


def test_admin_config_action_is_audited() -> None:
    """Создание помещения админом пишет строку аудита (метод+путь+роль)."""
    engine = _engine()
    client = _client(engine)
    resp = client.post("/api/v1/rooms", json=_ROOM, headers={"X-API-Key": "adkey"})
    assert resp.status_code == 200
    rows = list_audit(engine)
    assert len(rows) == 1
    assert rows[0]["action"] == "POST"
    assert rows[0]["target"] == "/api/v1/rooms"
    assert rows[0]["role"] == "admin"


def test_operator_ack_is_audited() -> None:
    """Подтверждение события оператором аудируется."""
    engine = _engine()
    client = _client(engine)
    resp = client.post(
        "/api/v1/events/11111111-1111-1111-1111-111111111111/ack",
        headers={"X-API-Key": "opkey"},
    )
    assert resp.status_code == 200
    rows = list_audit(engine)
    assert len(rows) == 1
    assert rows[0]["action"] == "POST"
    assert rows[0]["target"].endswith("/ack")
    assert rows[0]["role"] == "operator"


def test_forbidden_action_not_audited() -> None:
    """Запрещённое действие (operator → настройка) не пишет аудит (403 до записи)."""
    engine = _engine()
    client = _client(engine)
    resp = client.post("/api/v1/rooms", json=_ROOM, headers={"X-API-Key": "opkey"})
    assert resp.status_code == 403
    assert list_audit(engine) == []


def test_audit_endpoint_admin_only() -> None:
    """GET /audit доступен админу; оператор — 403."""
    engine = _engine()
    client = _client(engine)
    write_audit(engine, actor="admin", role="admin", action="POST", target="/x")
    ok_resp = client.get("/api/v1/audit", headers={"X-API-Key": "adkey"})
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["total"] == 1
    assert client.get("/api/v1/audit", headers={"X-API-Key": "opkey"}).status_code == 403


def test_audit_endpoint_time_filter() -> None:
    """Фильтр по времени в GET /audit отсекает старые записи."""
    engine = _engine()
    client = _client(engine)
    write_audit(
        engine,
        actor="admin",
        role="admin",
        action="POST",
        target="/old",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    write_audit(
        engine,
        actor="admin",
        role="admin",
        action="POST",
        target="/new",
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    resp = client.get(
        "/api/v1/audit", params={"from": "2026-03-01T00:00:00Z"}, headers={"X-API-Key": "adkey"}
    )
    targets = [i["target"] for i in resp.json()["data"]["items"]]
    assert targets == ["/new"]
