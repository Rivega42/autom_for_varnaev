"""Проверка машиночитаемых артефактов интеграции АУРА в пакете заказчика.

Гарантирует, что Postman-коллекция и OpenAPI-фрагмент корректно разбираются и
содержат все интеграционные эндпойнты (Приложение D руководства), чтобы артефакты
для разработчиков АУРА не протухали.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "docs/customer/integration"
POSTMAN = INTEGRATION_DIR / "aura_integration.postman_collection.json"
OPENAPI = INTEGRATION_DIR / "aura_integration.openapi.yaml"


def test_postman_collection_valid() -> None:
    """Postman-коллекция — валидный JSON со схемой v2.1 и всеми сценариями."""
    data = json.loads(POSTMAN.read_text(encoding="utf-8"))
    assert "v2.1.0" in data["info"]["schema"]
    keys = {v["key"] for v in data["variable"]}
    assert {"base_url", "api_key"} <= keys
    names = " ".join(item["name"] for item in data["item"])
    for marker in ("D.1", "D.2", "D.3", "D.4", "D.5"):
        assert marker in names, f"В коллекции нет запроса {marker}"


def test_openapi_fragment_valid() -> None:
    """OpenAPI-фрагмент — валидный YAML 3.x со всеми интеграционными путями."""
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.")
    assert {
        "/integration/analysis-tasks",
        "/integration/events",
        "/integration/settings",
        "/analysis-tasks/{id}",
    } <= set(spec["paths"])
    # вебхук готовности описан как callback на постановке задания
    assert "callbacks" in spec["paths"]["/integration/analysis-tasks"]["post"]
    # ключ X-API-Key объявлен схемой безопасности
    assert spec["components"]["securitySchemes"]["ApiKeyAuth"]["name"] == "X-API-Key"
