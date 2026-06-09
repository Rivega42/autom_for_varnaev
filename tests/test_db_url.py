"""Экранирование спецсимволов в URL подключения к БД (issue #214).

Все сборщики URL (сервисы + scripts/seed) собирают DSN из POSTGRES_*; пароль и
логин со спецсимволами (`#`, `@`, `:`, `/`, пробел) должны корректно переживать
разбор `make_url` — иначе подключение/миграции падают.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import make_url

# Модули, экспортирующие функцию сборки URL БД (имя функции — ниже).
_URL_MODULES = [
    ("api_gateway.db", "_database_url"),
    ("ingest_sensors.db", "_database_url"),
    ("log_service.db", "database_url"),
    ("scheduler.db", "database_url"),
    ("video_analytics.db", "database_url"),
    ("seed", "_database_url"),
]

_TRICKY_PASSWORD = "Cd566434##@x/y"


@pytest.mark.parametrize(("module_name", "func_name"), _URL_MODULES)
def test_special_chars_password_round_trip(
    module_name: str, func_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пароль со спецсимволами восстанавливается из URL без искажения."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "monitoring")
    monkeypatch.setenv("POSTGRES_PASSWORD", _TRICKY_PASSWORD)
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "monitoring")

    build_url = getattr(importlib.import_module(module_name), func_name)
    url = make_url(build_url())

    assert url.password == _TRICKY_PASSWORD
    assert url.username == "monitoring"
    assert url.host == "db"
    assert url.port == 5432
    assert url.database == "monitoring"


def test_explicit_database_url_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Готовый DATABASE_URL отдаётся как есть (без пересборки/экранирования)."""
    from api_gateway.db import _database_url

    explicit = "postgresql+psycopg2://u:p@h:5432/d"
    monkeypatch.setenv("DATABASE_URL", explicit)
    assert _database_url() == explicit
