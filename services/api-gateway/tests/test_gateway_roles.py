"""Тесты ролей и разграничения прав (#291): operator читает, admin настраивает."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from api_gateway.app import create_app
from api_gateway.config import Settings, parse_api_keys
from api_gateway.tables import metadata
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

_KEYS = {"opkey": "operator", "adkey": "admin"}


class _FakeEvents:
    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"items": [], "total": 0}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        return None

    def create_event(self, event: object) -> None:
        pass

    def ack_event(self, event_id: UUID) -> bool:
        return True


def _client(api_key: str | None = None, api_keys: dict[str, str] | None = None) -> TestClient:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=api_key,
        aura_integration_enabled=False,
        api_keys=api_keys or {},
    )
    return TestClient(create_app(settings=settings, engine=engine, events_client=_FakeEvents()))


_ROOM = {"id": "room-01", "name": "Цех", "is_cold": False}


# ── parse_api_keys ──


def test_parse_api_keys_valid_and_garbage() -> None:
    """Разбор валидных пар и пропуск мусора/неизвестных ролей."""
    parsed = parse_api_keys("k1:operator, k2:admin ,bad, k3:superuser, :admin, k4:")
    assert parsed == {"k1": "operator", "k2": "admin"}


def test_parse_api_keys_empty() -> None:
    """Пусто/None → пустая карта."""
    assert parse_api_keys(None) == {}
    assert parse_api_keys("") == {}


def test_parse_api_keys_duplicate_keeps_first() -> None:
    """Дубликат ключа не повышает роль молча — остаётся первая."""
    assert parse_api_keys("k:operator,k:admin") == {"k": "operator"}


def test_from_env_fails_closed_on_broken_api_keys(monkeypatch: Any) -> None:
    """API_KEYS задан, но весь мусор, и нет API_KEY → ошибка старта (не fail-open)."""
    import pytest

    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("API_KEYS", "garbage,also:bad")
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_from_env_no_keys_is_allowed(monkeypatch: Any) -> None:
    """Полное отсутствие ключей — допустимо (dev/тесты): проверка отключена."""
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)
    assert Settings.from_env().auth_enabled() is False


# ── Разграничение по ролям ──


def test_operator_can_read_but_not_configure() -> None:
    """Оператор читает справочник, но получает 403 на создание помещения."""
    client = _client(api_keys=_KEYS)
    assert client.get("/api/v1/rooms", headers={"X-API-Key": "opkey"}).status_code == 200
    resp = client.post("/api/v1/rooms", json=_ROOM, headers={"X-API-Key": "opkey"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_admin_can_configure() -> None:
    """Админ создаёт помещение (200)."""
    client = _client(api_keys=_KEYS)
    resp = client.post("/api/v1/rooms", json=_ROOM, headers={"X-API-Key": "adkey"})
    assert resp.status_code == 200


def test_operator_can_ack() -> None:
    """Оператор может подтверждать события (ack — не настройка)."""
    client = _client(api_keys=_KEYS)
    resp = client.post(
        "/api/v1/events/11111111-1111-1111-1111-111111111111/ack",
        headers={"X-API-Key": "opkey"},
    )
    assert resp.status_code == 200


def test_missing_or_bad_key_unauthorized() -> None:
    """Без ключа или с неверным ключом — 401."""
    client = _client(api_keys=_KEYS)
    assert client.get("/api/v1/rooms").status_code == 401
    assert client.get("/api/v1/rooms", headers={"X-API-Key": "nope"}).status_code == 401


def test_legacy_api_key_is_admin() -> None:
    """Совместимость: legacy API_KEY = роль admin (может настраивать)."""
    client = _client(api_key="legacy")
    assert (
        client.post("/api/v1/rooms", json=_ROOM, headers={"X-API-Key": "legacy"}).status_code == 200
    )


def test_no_keys_configured_fail_open() -> None:
    """Без настроенных ключей проверка отключена (dev): доступ как admin."""
    client = _client()
    assert client.get("/api/v1/rooms").status_code == 200
    assert client.post("/api/v1/rooms", json=_ROOM).status_code == 200
