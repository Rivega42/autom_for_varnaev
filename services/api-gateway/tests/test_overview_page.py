"""Обзорный экран дежурного: страница /ui/overview.html поверх GET /overview (#289)."""

from __future__ import annotations

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


def _client() -> TestClient:
    return TestClient(create_app(settings=_SETTINGS, engine=_engine()))


def test_overview_page_served() -> None:
    """Экран дежурного отдаётся под /ui/overview.html и опирается на GET /overview."""
    resp = _client().get("/ui/overview.html")
    assert resp.status_code == 200
    assert "Обзор объекта" in resp.text
    assert "/overview" in resp.text, "Страница должна ходить в агрегирующий эндпойнт"
    assert "X-API-Key" in resp.text, "Запросы к API — с ключом в заголовке"


def test_overview_page_autorefreshes() -> None:
    """На странице есть автообновление (setInterval по таймеру)."""
    text = _client().get("/ui/overview.html").text
    assert "setInterval(load" in text
    assert "REFRESH_MS" in text


def test_index_links_to_overview() -> None:
    """GUI настройки ссылается на обзорный экран."""
    resp = _client().get("/ui/")
    assert resp.status_code == 200
    assert "overview.html" in resp.text
