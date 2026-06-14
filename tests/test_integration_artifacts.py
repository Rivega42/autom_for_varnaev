"""Артефакты интеграции с АУРА (integration/) валидны и не разошлись с кодом.

Postman-коллекция и OpenAPI-фрагмент — машиночитаемое описание разъёмов АУРА для
их разработчиков. Тест: файлы парсятся, содержат сценарии D.1–D.5, а пути
OpenAPI-фрагмента совпадают с реально зарегистрированными разъёмами `/integration/*`
внешнего шлюза (фрагмент не должен устаревать относительно кода).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from api_gateway.app import create_app
from api_gateway.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
_POSTMAN = REPO_ROOT / "integration" / "aura_integration.postman_collection.json"
_OPENAPI = REPO_ROOT / "integration" / "aura_integration.openapi.yaml"

# Разъёмы АУРА, которые фрагмент обязан описывать (полные пути).
_INTEGRATION_PATHS = {
    "/integration/analysis-tasks",
    "/integration/events",
    "/integration/settings",
}


def test_postman_collection_valid() -> None:
    """Коллекция парсится, имеет переменные base_url/api_key и сценарии D.1–D.5."""
    data = json.loads(_POSTMAN.read_text(encoding="utf-8"))
    assert data["info"]["schema"].startswith("https://schema.getpostman.com/json/collection/v2.1.0")
    var_keys = {v["key"] for v in data["variable"]}
    assert {"base_url", "api_key"} <= var_keys
    names = " ".join(item["name"] for item in data["item"])
    for tag in ("D.1", "D.2", "D.3", "D.4", "D.5"):
        assert tag in names, f"В коллекции нет сценария {tag}"
    # Запросы используют переменные, а не зашитый адрес/ключ.
    raw = _POSTMAN.read_text(encoding="utf-8")
    assert "{{base_url}}" in raw and "{{api_key}}" in raw


def test_openapi_fragment_valid() -> None:
    """OpenAPI-фрагмент парсится: версия, security X-API-Key, поведение 501."""
    spec = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.1")
    schemes = spec["components"]["securitySchemes"]
    assert any(s.get("name") == "X-API-Key" for s in schemes.values())
    text = _OPENAPI.read_text(encoding="utf-8")
    assert "NOT_IMPLEMENTED" in text and "501" in text  # граница v1


def test_openapi_paths_match_registered_routes() -> None:
    """Пути /integration/* фрагмента совпадают с разъёмами реального шлюза."""
    spec = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    fragment_integration = {p for p in spec["paths"] if p.startswith("/integration/")}
    assert fragment_integration == _INTEGRATION_PATHS

    settings = Settings(
        log_service_url="http://log-service:8000", api_key=None, aura_integration_enabled=False
    )
    registered = {
        path[len("/api/v1") :]
        for path in create_app(settings=settings).openapi()["paths"]
        if path.startswith("/api/v1/integration/")
    }
    assert fragment_integration == registered, "OpenAPI-фрагмент разошёлся с кодом разъёмов"
