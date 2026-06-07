"""Проверка provisioning datasource Grafana (TimescaleDB, ro-пользователь)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_DATASOURCE = REPO_ROOT / "grafana/provisioning/datasources/timescaledb.yaml"
_INIT_RO = REPO_ROOT / "db/init/02_grafana_ro.sh"


def _load() -> dict[str, Any]:
    data = yaml.safe_load(_DATASOURCE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_datasource_points_to_db() -> None:
    """Datasource типа postgres смотрит на db:5432 и включает timescaledb."""
    ds = _load()["datasources"][0]
    assert ds["type"] == "postgres"
    assert ds["url"] == "db:5432"
    assert ds["jsonData"]["timescaledb"] is True
    assert ds["jsonData"]["sslmode"] == "disable"


def test_datasource_uses_ro_credentials_from_env() -> None:
    """Пользователь и пароль datasource берутся из env (ro-пользователь)."""
    ds = _load()["datasources"][0]
    assert ds["user"] == "${POSTGRES_RO_USER}"
    assert ds["secureJsonData"]["password"] == "${POSTGRES_RO_PASSWORD}"
    assert ds["database"] == "${POSTGRES_DB}"


def test_ro_init_script_present() -> None:
    """Init-скрипт создания ro-пользователя на месте и использует env-креды."""
    text = _INIT_RO.read_text(encoding="utf-8")
    assert "CREATE ROLE" in text
    assert "POSTGRES_RO_USER" in text
    assert "GRANT SELECT" in text
