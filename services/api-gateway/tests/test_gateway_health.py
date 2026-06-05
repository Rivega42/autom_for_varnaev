"""Проверка healthcheck api-gateway и формы конверта."""

from __future__ import annotations

from api_gateway.app import create_app
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    """GET /api/v1/health возвращает конверт со status=ok."""
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"] == {"service": "api-gateway", "up": True}
    assert body["error"] is None
    assert "ts" in body
