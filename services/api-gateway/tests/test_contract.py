"""Контрактные тесты api-gateway: форма конверта и 501 разъёмов АУРА.

Проверяем соответствие docs/03_API_CONTRACT.md §1.1–§1.2 и §4: успешный и
ошибочный ответы валидны по общей модели `Envelope`, разъёмы `/integration/*`
в v1 отдают 501 NOT_IMPLEMENTED.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import metadata
from fakes import FakeEventsClient
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from monitoring_shared import Envelope

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key=None,
    aura_integration_enabled=False,
)

_ENVELOPE_KEYS = {"status", "data", "error", "ts"}


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _client() -> TestClient:
    # engine нужен: режим интеграции с АУРА читается из app_config (#352).
    return TestClient(
        create_app(settings=_SETTINGS, events_client=FakeEventsClient(), engine=_engine())
    )


def test_success_envelope_conforms() -> None:
    """Успешный ответ — ровно поля конверта, status=ok, error=null, валиден."""
    body = _client().get("/api/v1/health").json()
    assert set(body.keys()) == _ENVELOPE_KEYS
    assert body["status"] == "ok"
    assert body["error"] is None
    assert body["data"] is not None
    Envelope.model_validate(body)


def test_error_envelope_conforms() -> None:
    """Ответ-ошибка (404) — status=error, data=null, есть error.code/message."""
    body = _client().get(f"/api/v1/events/{uuid4()}").json()
    assert set(body.keys()) == _ENVELOPE_KEYS
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"]["code"] == "EVENT_NOT_FOUND"
    assert body["error"]["message"]
    Envelope.model_validate(body)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/integration/analysis-tasks"),
        ("get", "/api/v1/integration/events"),
        ("put", "/api/v1/integration/settings"),
    ],
)
def test_integration_disabled_returns_501(method: str, path: str) -> None:
    """Каждый разъём АУРА при флаге=false → 501 NOT_IMPLEMENTED в конверте."""
    resp = getattr(_client(), method)(path)
    assert resp.status_code == 501
    body = resp.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    Envelope.model_validate(body)


def test_limit_is_capped() -> None:
    """Запредельный limit отклоняется валидацией (защита от OOM одним запросом)."""
    resp = _client().get("/api/v1/events", params={"limit": 999999})
    assert resp.status_code == 422


def test_naive_datetime_accepted_as_utc() -> None:
    """Время без зоны в from/to принимается (трактуется как UTC), а не 500."""
    resp = _client().get("/api/v1/events", params={"from": "2026-06-01T10:00:00"})
    assert resp.status_code == 200
