"""Проверка эндпойнтов событий api-gateway (с фейковым клиентом log-service)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from api_gateway.app import create_app
from api_gateway.config import Settings
from fastapi.testclient import TestClient


class _FakeEventsClient:
    """Фейковый источник событий: фиксирует переданные фильтры."""

    def __init__(self, event: dict[str, Any] | None) -> None:
        self._event = event
        self.last_params: dict[str, Any] | None = None

    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        self.last_params = params
        items = [self._event] if self._event else []
        return {"items": items, "total": len(items)}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        if self._event and self._event["id"] == str(event_id):
            return self._event
        return None

    def create_event(self, event: object) -> None:
        self.created = getattr(self, "created", [])
        self.created.append(event)

    def ack_event(self, event_id: UUID) -> bool:
        # подтверждается только «существующее» событие фейка
        return bool(self._event and self._event["id"] == str(event_id))


_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key=None,
    aura_integration_enabled=False,
)


def _event() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "ts": "2026-06-05T10:30:00Z",
        "source": "sensors",
        "type": "threshold_exceeded",
        "room": "room-01",
        "severity": "warning",
        "message": "В холодильной камере температура выше нормы",
        "payload": {"metric": "air_temp", "value": 8.7, "threshold": 8.0},
        "artifact_path": None,
    }


def test_list_events_wraps_payload() -> None:
    """GET /events отдаёт конверт ok с items/total и пробрасывает фильтры."""
    ev = _event()
    fake = _FakeEventsClient(ev)
    client = TestClient(create_app(settings=_SETTINGS, events_client=fake))
    resp = client.get("/api/v1/events", params={"room": "room-01", "type": "threshold_exceeded"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["room"] == "room-01"
    assert fake.last_params is not None
    assert fake.last_params["room"] == "room-01"
    assert fake.last_params["type"] == "threshold_exceeded"


def test_list_events_invalid_dates_rejected() -> None:
    """Кривые from/to в GET /events → 422 ещё в шлюзе, без похода в log-service (#205)."""
    fake = _FakeEventsClient(None)
    client = TestClient(create_app(settings=_SETTINGS, events_client=fake))
    for params in ({"from": "не-дата"}, {"to": "2026-13-45"}):
        resp = client.get("/api/v1/events", params=params)
        assert resp.status_code == 422, params
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.last_params is None, "Запрос не должен был дойти до log-service"

    # Валидные даты (включая без зоны — трактуются как UTC) проходят как раньше.
    okresp = client.get(
        "/api/v1/events", params={"from": "2026-06-01T00:00:00", "to": "2026-06-05T10:30:00Z"}
    )
    assert okresp.status_code == 200
    assert fake.last_params is not None
    assert fake.last_params["from"] == "2026-06-01T00:00:00"


def test_get_event_found() -> None:
    """GET /events/{id} существующего события → конверт ok."""
    ev = _event()
    client = TestClient(create_app(settings=_SETTINGS, events_client=_FakeEventsClient(ev)))
    resp = client.get(f"/api/v1/events/{ev['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == ev["id"]


def test_get_event_missing() -> None:
    """GET /events/{id} отсутствующего → 404 EVENT_NOT_FOUND в конверте."""
    client = TestClient(create_app(settings=_SETTINGS, events_client=_FakeEventsClient(None)))
    resp = client.get(f"/api/v1/events/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_post_analytics_event_persisted() -> None:
    """POST /analytics-events создаёт событие source=analytics, origin=browser."""
    fake = _FakeEventsClient(None)
    client = TestClient(create_app(settings=_SETTINGS, events_client=fake))
    resp = client.post(
        "/api/v1/analytics-events",
        json={"room": "room-01", "message": "Стол протёрт (правой рукой, 5 с)"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"]
    created = getattr(fake, "created", [])
    assert len(created) == 1
    ev = created[0]
    assert ev.source.value == "analytics"
    assert ev.type.value == "action_detected"
    assert ev.room_id == "room-01"
    assert ev.payload["origin"] == "browser"
    assert "Стол протёрт" in ev.message


def test_ack_event_ok_and_404() -> None:
    """POST /events/{id}/ack: подтверждение существующего; 404 для чужого id."""
    ev = _event()
    client = TestClient(create_app(settings=_SETTINGS, events_client=_FakeEventsClient(ev)))
    okresp = client.post(f"/api/v1/events/{ev['id']}/ack")
    assert okresp.status_code == 200
    assert okresp.json()["data"]["acknowledged"] is True

    missing = client.post(f"/api/v1/events/{uuid4()}/ack")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"
