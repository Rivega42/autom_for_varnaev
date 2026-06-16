"""Разъёмы АУРА /integration/*: заглушки за фичефлагом и реализованные D.1/D.3."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.integration import require_aura_enabled
from api_gateway.tables import analysis_tasks, metadata
from fakes import FakeEventsClient
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool


def _settings(enabled: bool) -> Settings:
    return Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=enabled,
    )


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _client(enabled: bool, events: FakeEventsClient | None = None) -> TestClient:
    # engine нужен: действующий режим интеграции читается из app_config (#352).
    return TestClient(
        create_app(settings=_settings(enabled), events_client=events, engine=_engine())
    )


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
    """При включённой интеграции страж не бросает исключение."""
    require_aura_enabled(True)  # не должно бросить


def test_guard_blocks_when_disabled() -> None:
    """При выключенной интеграции страж бросает 501."""
    with pytest.raises(HTTPException) as exc:
        require_aura_enabled(False)
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
    fake = FakeEventsClient(_event())
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
    fake = FakeEventsClient()
    client = _client(enabled=True, events=fake)
    resp = client.get("/api/v1/integration/events", params={"limit": 200, "offset": 400})
    assert resp.status_code == 200
    assert fake.last_params is not None
    assert fake.last_params["limit"] == 200
    assert fake.last_params["offset"] == 400


def test_integration_events_invalid_date_422_when_enabled() -> None:
    """Кривая дата в D.3 → 422 ещё в шлюзе, без похода в log-service (#205)."""
    fake = FakeEventsClient()
    client = _client(enabled=True, events=fake)
    resp = client.get("/api/v1/integration/events", params={"from": "не-дата"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.last_params is None, "Запрос не должен был дойти до log-service"


def test_integration_events_disabled_still_501() -> None:
    """Флаг выключен → D.3 по-прежнему 501, источник событий не вызывается."""
    fake = FakeEventsClient(_event())
    client = _client(enabled=False, events=fake)
    resp = client.get("/api/v1/integration/events", params={"type": "coverage_report"})
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"
    assert fake.last_params is None


# ── Тумблер интеграции с АУРА из GUI (PUT /aura/status, без перезапуска, #352) ──


def test_aura_toggle_enables_without_restart() -> None:
    """PUT /aura/status включает интеграцию — D.3 отвечает без перезапуска; и обратно."""
    fake = FakeEventsClient(_event())
    client = _client(enabled=False, events=fake)  # env-флаг ВЫКЛ

    # До тумблера: статус выключен и D.3 заглушён.
    assert client.get("/api/v1/aura/status").json()["data"]["enabled"] is False
    assert client.get("/api/v1/integration/events").status_code == 501

    # Включаем тумблером (БД-настройка приоритетнее env).
    put = client.put("/api/v1/aura/status", json={"enabled": True})
    assert put.status_code == 200
    assert put.json()["data"] == {"enabled": True, "source": "db"}

    # Теперь D.3 отвечает данными — без перезапуска сервиса.
    resp = client.get("/api/v1/integration/events")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1
    assert client.get("/api/v1/aura/status").json()["data"]["enabled"] is True

    # Выключаем обратно — снова 501.
    client.put("/api/v1/aura/status", json={"enabled": False})
    assert client.get("/api/v1/integration/events").status_code == 501


# ── D.1: POST /integration/analysis-tasks — приём задания от АУРА (#348) ──

_TASK_BODY = {
    "source_type": "file",
    "source_ref": "/data/artifacts/2026-06-05/clip-0007.mp4",
    "room": "room-03",
    "pipeline": "pose_v1",
    "callback_url": "http://aura/notify",
}


def test_integration_post_task_creates_aura_task_when_enabled() -> None:
    """Флаг включён → D.1 создаёт задание trigger=aura, status=queued; callback_url в БД."""
    eng = _engine()
    client = TestClient(
        create_app(settings=_settings(True), events_client=FakeEventsClient(), engine=eng)
    )
    resp = client.post("/api/v1/integration/analysis-tasks", json=_TASK_BODY)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["trigger"] == "aura"
    assert data["status"] == "queued"
    assert data["source_ref"] == _TASK_BODY["source_ref"]
    assert data["room"] == "room-03"
    # callback_url сохранён в БД (в ответе не отдаём — input-only для D.5).
    # Через таблицу + UUID: SQLite хранит sa.Uuid как hex без дефисов.
    with eng.connect() as conn:
        row = (
            conn.execute(
                select(analysis_tasks.c.callback_url, analysis_tasks.c.trigger).where(
                    analysis_tasks.c.id == UUID(data["id"])
                )
            )
            .mappings()
            .first()
        )
    assert row is not None
    assert row["callback_url"] == "http://aura/notify"
    assert row["trigger"] == "aura"


def test_integration_post_task_disabled_501() -> None:
    """Флаг выключен → D.1 отдаёт 501 даже с валидным телом (задание не создаётся)."""
    client = _client(enabled=False)
    resp = client.post("/api/v1/integration/analysis-tasks", json=_TASK_BODY)
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_integration_post_task_empty_body_422_when_enabled() -> None:
    """Флаг включён, но тело пустое → 422 (а не падение)."""
    client = _client(enabled=True)
    resp = client.post("/api/v1/integration/analysis-tasks")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_integration_post_task_disabled_malformed_still_501() -> None:
    """Граница v1: выключенный разъём отдаёт 501 ДАЖЕ на кривое тело (не 422)."""
    client = _client(enabled=False)
    resp = client.post(
        "/api/v1/integration/analysis-tasks",
        content=b"{bad-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_integration_post_task_invalid_callback_422_when_enabled() -> None:
    """Флаг включён, callback_url не http(s) → 422 (лёгкая валидация формата)."""
    client = _client(enabled=True)
    bad = {**_TASK_BODY, "callback_url": "ftp://aura/notify"}
    resp = client.post("/api/v1/integration/analysis-tasks", json=bad)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
