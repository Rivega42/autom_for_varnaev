"""Проверка healthcheck log-service."""

from fastapi.testclient import TestClient
from log_service.app import create_app


def test_health_ok() -> None:
    """GET /health возвращает конверт со status=ok."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["service"] == "log-service"
