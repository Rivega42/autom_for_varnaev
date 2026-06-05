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
