"""Сверка OpenAPI api-gateway с контрактом (docs/03_API_CONTRACT.md §3–§4).

OpenAPI — машинно-читаемая версия контракта (§6). Тест ловит расхождение:
если из приложения исчез или появился путь, не отражённый в контракте, набор
`(метод, путь)` перестанет совпадать с ожидаемым.
"""

from __future__ import annotations

from typing import Any

from api_gateway.app import create_app
from api_gateway.config import Settings
from fastapi.testclient import TestClient

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key=None,
    aura_integration_enabled=False,
)

# Ожидаемый набор операций контракта (docs/03_API_CONTRACT.md §3–§4).
_EXPECTED_OPERATIONS: set[tuple[str, str]] = {
    ("get", "/api/v1/health"),
    ("get", "/api/v1/events"),
    ("get", "/api/v1/events/{event_id}"),
    ("post", "/api/v1/events/{event_id}/ack"),
    ("post", "/api/v1/analytics-events"),
    ("get", "/api/v1/artifacts/{artifact_id}"),
    ("post", "/api/v1/analysis-tasks"),
    ("get", "/api/v1/analysis-tasks"),
    ("get", "/api/v1/analysis-tasks/{task_id}"),
    ("get", "/api/v1/readings"),
    ("get", "/api/v1/reports/sanitation"),
    ("get", "/api/v1/overview"),
    ("get", "/api/v1/audit"),
    ("get", "/api/v1/rooms"),
    ("post", "/api/v1/rooms"),
    ("get", "/api/v1/sensor-nodes"),
    ("post", "/api/v1/sensor-nodes"),
    ("get", "/api/v1/cameras"),
    ("post", "/api/v1/cameras"),
    ("get", "/api/v1/cameras/{camera_id}"),
    ("patch", "/api/v1/cameras/{camera_id}"),
    ("get", "/api/v1/cameras/{camera_id}/snapshot"),
    ("get", "/api/v1/cameras/{camera_id}/stream.mjpeg"),
    ("get", "/api/v1/cameras/{camera_id}/zones"),
    ("post", "/api/v1/cameras/{camera_id}/zones"),
    ("patch", "/api/v1/zones/{zone_id}"),
    ("delete", "/api/v1/zones/{zone_id}"),
    ("get", "/api/v1/cleaning-rules"),
    ("post", "/api/v1/cleaning-rules"),
    ("patch", "/api/v1/cleaning-rules/{rule_id}"),
    ("delete", "/api/v1/cleaning-rules/{rule_id}"),
    ("get", "/api/v1/thresholds"),
    ("post", "/api/v1/thresholds"),
    ("patch", "/api/v1/thresholds/{threshold_id}"),
    ("delete", "/api/v1/thresholds/{threshold_id}"),
    ("get", "/api/v1/schedules"),
    ("post", "/api/v1/schedules"),
    ("patch", "/api/v1/schedules/{schedule_id}"),
    ("delete", "/api/v1/schedules/{schedule_id}"),
    ("post", "/api/v1/integration/analysis-tasks"),
    ("get", "/api/v1/integration/events"),
    ("put", "/api/v1/integration/settings"),
}


def _operations(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Собрать множество (метод, путь) из OpenAPI-схемы."""
    ops: set[tuple[str, str]] = set()
    for path, methods in schema["paths"].items():
        for method in methods:
            ops.add((method.lower(), path))
    return ops


def test_openapi_matches_contract() -> None:
    """Набор операций OpenAPI совпадает с ожидаемым набором контракта."""
    app = create_app(settings=_SETTINGS)
    assert _operations(app.openapi()) == _EXPECTED_OPERATIONS


def test_openapi_json_served() -> None:
    """/openapi.json доступен и содержит пути контракта."""
    client = TestClient(create_app(settings=_SETTINGS))
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/integration/events" in paths
