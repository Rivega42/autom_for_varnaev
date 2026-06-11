"""Проверка структуры миграции 0018 (#295): свёртка + политики TimescaleDB.

DDL TimescaleDB прогоняется только на сервере с расширением (хост), поэтому здесь
проверяем, что миграция объявляет верную ревизию и содержит нужные конструкции:
continuous aggregate, политику обновления, сжатие, retention (env-gated), и что
весь timescale-DDL обёрнут в autocommit_block.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_MIGRATION = REPO_ROOT / "db/migrations/versions/0018_readings_rollup.py"


def _source() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def test_migration_exists_and_chains() -> None:
    """Файл существует и продолжает цепочку от 0017."""
    spec = importlib.util.spec_from_file_location("m0018", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0018_readings_rollup"
    assert module.down_revision == "0017_audit_log"


def test_creates_continuous_aggregate() -> None:
    """Объявлена почасовая свёртка с avg/min/max и политикой обновления."""
    src = _source()
    assert "timescaledb.continuous" in src
    assert "sensor_readings_hourly" in src
    assert "time_bucket('1 hour', ts)" in src
    for agg in ("avg(value)", "min(value)", "max(value)"):
        assert agg in src
    assert "add_continuous_aggregate_policy" in src


def test_compression_and_retention_policies() -> None:
    """Есть сжатие (lossless) и retention из env (по умолчанию выключен)."""
    src = _source()
    assert "timescaledb.compress" in src
    assert "add_compression_policy" in src
    assert "READINGS_COMPRESS_AFTER_DAYS" in src
    assert "READINGS_RETENTION_DAYS" in src
    assert "add_retention_policy" in src


def test_timescale_ddl_in_autocommit_block() -> None:
    """Timescale-DDL вне транзакции Alembic (autocommit_block)."""
    assert "autocommit_block()" in _source()


def test_downgrade_drops_view_and_policies() -> None:
    """downgrade снимает политики и удаляет свёртку."""
    src = _source()
    assert "DROP MATERIALIZED VIEW IF EXISTS sensor_readings_hourly" in src
    assert "remove_compression_policy" in src
