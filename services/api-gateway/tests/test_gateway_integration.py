"""Проверка заглушённых разъёмов АУРА /integration/* (501 за фичефлагом)."""

from __future__ import annotations

import pytest
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.integration import require_aura_enabled
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _settings(enabled: bool) -> Settings:
    return Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=enabled,
    )


def _client(enabled: bool) -> TestClient:
    return TestClient(create_app(settings=_settings(enabled)))


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
