"""Smoke-тест docker-compose: валидность YAML и наличие сервиса grafana.

Проверяет, что Grafana поднята в compose согласно docs/02_NETWORK.md §3
(сеть internal, публикация порта наружу).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict[str, Any]:
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert isinstance(data, dict)
    return data


def test_compose_is_valid_yaml() -> None:
    """docker-compose.yml парсится и содержит секции services/networks/volumes."""
    compose = _compose()
    assert "services" in compose
    assert "networks" in compose
    assert "volumes" in compose


def test_grafana_service_present() -> None:
    """Сервис grafana — на сети internal, публикует порт, монтирует provisioning."""
    grafana = _compose()["services"].get("grafana")
    assert grafana is not None, "Сервис grafana отсутствует в compose"
    assert "internal" in grafana["networks"]
    assert any("3000" in str(p) for p in grafana["ports"]), "Порт дашборда не опубликован"
    mounts = " ".join(grafana["volumes"])
    assert "provisioning" in mounts
    assert "dashboards" in mounts


def test_grafana_volume_declared() -> None:
    """Том grafana_data объявлен в секции volumes."""
    assert "grafana_data" in _compose()["volumes"]


# ── Финальный compose (E9.6): прикладные сервисы ──

# Внутренние сервисы (наружу не публикуются, только сеть internal).
_INTERNAL_ONLY = ("log-service", "ingest-sensors", "scheduler", "video-analytics")


def test_all_app_services_present_with_build() -> None:
    """Все пять наших сервисов присутствуют и собираются из своих Dockerfile."""
    services = _compose()["services"]
    for name in ("api-gateway", "log-service", "ingest-sensors", "scheduler", "video-analytics"):
        assert name in services, f"Сервис {name} отсутствует в compose"
        build = services[name]["build"]
        assert build["dockerfile"] == f"services/{name}/Dockerfile"
        assert build["context"] == "."


def test_internal_services_not_published() -> None:
    """Внутренние сервисы не публикуют портов наружу и сидят только в internal."""
    services = _compose()["services"]
    for name in _INTERNAL_ONLY:
        svc = services[name]
        assert "ports" not in svc, f"{name} не должен публиковать порт наружу"
        assert svc["networks"] == ["internal"]


def test_api_gateway_bridges_networks_and_published() -> None:
    """api-gateway — в обеих сетях (internal+integration) и единственный с REST наружу."""
    gateway = _compose()["services"]["api-gateway"]
    assert set(gateway["networks"]) == {"internal", "integration"}
    assert any("8000" in str(p) for p in gateway["ports"]), "REST-порт не опубликован"


def test_video_analytics_mounts_artifacts() -> None:
    """video-analytics монтирует общий том artifacts."""
    va = _compose()["services"]["video-analytics"]
    assert any("artifacts:/data/artifacts" in v for v in va["volumes"])
