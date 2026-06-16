"""Проверка аутентификации по X-API-Key на публичных и /integration/*."""

from __future__ import annotations

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import metadata
from fakes import FakeEventsClient
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_KEY = "secret-key"


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _client(enabled_aura: bool = False) -> TestClient:
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=_KEY,
        aura_integration_enabled=enabled_aura,
    )
    # engine нужен: режим интеграции с АУРА читается из app_config (#352).
    return TestClient(
        create_app(settings=settings, events_client=FakeEventsClient(), engine=_engine())
    )


def test_health_open_without_key() -> None:
    """/health доступен без ключа."""
    assert _client().get("/api/v1/health").status_code == 200


def test_protected_requires_key() -> None:
    """Публичный эндпойнт без ключа → 401 UNAUTHORIZED в конверте."""
    resp = _client().get("/api/v1/events")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_protected_wrong_key() -> None:
    """Неверный ключ → 401."""
    resp = _client().get("/api/v1/events", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_protected_with_correct_key() -> None:
    """Верный ключ пропускает к обработчику."""
    resp = _client().get("/api/v1/events", headers={"X-API-Key": _KEY})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_integration_requires_key_before_stub() -> None:
    """/integration/* без ключа → 401 (раньше, чем 501-заглушка)."""
    resp = _client().get("/api/v1/integration/events")
    assert resp.status_code == 401


def test_integration_with_key_returns_stub() -> None:
    """С верным ключом, но выключенной интеграцией → 501 NOT_IMPLEMENTED."""
    resp = _client().get("/api/v1/integration/events", headers={"X-API-Key": _KEY})
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"
