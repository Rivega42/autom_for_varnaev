"""app_config: ключ-значение настроек контура (хранение ключа лицензии из GUI, #335)."""

from __future__ import annotations

from datetime import UTC, datetime

from api_gateway.app_config_repository import clear_config, get_config, set_config
from api_gateway.tables import metadata
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_NOW = datetime(2026, 6, 14, tzinfo=UTC)


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def test_get_missing_returns_none() -> None:
    """Несуществующий ключ → None."""
    assert get_config(_engine(), "license_key") is None


def test_set_then_get() -> None:
    """Значение сохраняется и читается по ключу."""
    eng = _engine()
    set_config(eng, "license_key", "abc.def", _NOW)
    assert get_config(eng, "license_key") == "abc.def"


def test_set_twice_updates_in_place() -> None:
    """Повторный set по тому же ключу — обновление, а не дубль (UPSERT-путь UPDATE)."""
    eng = _engine()
    set_config(eng, "license_key", "first", _NOW)
    set_config(eng, "license_key", "second", _NOW)
    assert get_config(eng, "license_key") == "second"


def test_clear_removes_key() -> None:
    """clear_config удаляет настройку — get снова отдаёт None."""
    eng = _engine()
    set_config(eng, "license_key", "x", _NOW)
    clear_config(eng, "license_key")
    assert get_config(eng, "license_key") is None
