"""Разъёмы АУРА /integration/*: заглушки за фичефлагом и реализованный D.3 (события)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.integration import require_aura_enabled
from fastapi import HTTPException
from fastapi.testclient import TestClient


class _FakeEventsClient:
    """Фейковый источник событий: фиксирует переданные фильтры."""

    def __init__(self, event: dict[str, Any] | None = None) -> None:
        self._event = event
        self.last_params: dict[str, Any] | None = None

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        self.last_params = params
        items = [self._event] if self._event else []
        return {"items": items, "total": len(items)}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        return None

    def create_event(self, event: object) -> None:
        pass

    def ack_event(self, event_id: UUID) -> bool:
        return False


def _settings(enabled: bool) -> Settings:
    return Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=enabled,
    )


def _client(enabled: bool, events: _FakeEventsClient | None = None) -> TestClient:
    return TestClient(create_app(settings=_settings(enabled), events_client=events))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/integration/analysis-tasks"),
        ("get", "/api/v1/integration/events"),
        ("put", "/api/v1/integration/settings"),
    ],
)
def test_integration_stub_returns_501(method: str, path: str) -> None:
    """При выключенном флаге каждый разъём отдаёт 501 NOT_IMPLEMENTED в конверте."""
    client = _client(enabled=False)
    resp = getattr(client, method)(path)
    assert resp.status_code == 501
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


def test_guard_passes_when_enabled() -> None:
    """При включённом флаге страж не бросает исключение."""
    require_aura_enabled(_settings(enabled=True))  # не должно бросить


def test_guard_blocks_when_disabled() -> None:
    """При выключенном флаге страж бросает 501."""
    with pytest.raises(HTTPException) as exc:
        require_aura_enabled(_settings(enabled=False))
    assert exc.value.status_code == 501


# ── D.3: GET /integration/events отдаёт события при включённом флаге (#347) ──


def _event() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "ts": "2026-06-08T10:30:00Z",
        "source": "sensors",
        "type": "coverage_report",
        "room": "room-03",
        "severity": "info",
        "message": "Зона убрана",
        "payload": {},
        "artifact_path": None,
    }


def test_integration_events_returns_data_when_enabled() -> None:
    """Флаг включён → D.3 отдаёт конверт ok с событиями и пробрасывает фильтр type."""
    fake = _FakeEventsClient(_event())
    client = _client(enabled=True, events=fake)
    resp = client.get(
        "/api/v1/integration/events",
        params={"from": "2026-06-08T00:00:00Z", "type": "coverage_report"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["type"] == "coverage_report"
    # Фильтры дошли до источника событий (room в D.3 не предусмотрен контрактом).
    assert fake.last_params is not None
    assert fake.last_params["type"] == "coverage_report"
    assert fake.last_params["from"] == "2026-06-08T00:00:00Z"
    # Пагинация: дефолтные limit/offset проброшены (иначе log-service режет до 50).
    assert fake.last_params["limit"] == 50
    assert fake.last_params["offset"] == 0


def test_integration_events_pagination_passed_through() -> None:
    """D.3 пробрасывает явные limit/offset в источник событий (постраничный забор)."""
    fake = _FakeEventsClient()
    client = _client(enabled=True, events=fake)
    resp = client.get("/api/v1/integration/events", params={"limit": 200, "offset": 400})
    assert resp.status_code == 200
    assert fake.last_params is not None
    assert fake.last_params["limit"] == 200
    assert fake.last_params["offset"] == 400


def test_integration_events_invalid_date_422_when_enabled() -> None:
    """Кривая дата в D.3 → 422 ещё в шлюзе, без похода в log-service (#205)."""
    fake = _FakeEventsClient()
    client = _client(enabled=True, events=fake)
    resp = client.get("/api/v1/integration/events", params={"from": "не-дата"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.last_params is None, "Запрос не должен был дойти до log-service"


def test_integration_events_disabled_still_501() -> None:
    """Флаг выключен → D.3 по-прежнему 501, источник событий не вызывается."""
    fake = _FakeEventsClient(_event())
    client = _client(enabled=False, events=fake)
    resp = client.get("/api/v1/integration/events", params={"type": "coverage_report"})
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"
    assert fake.last_params is None
