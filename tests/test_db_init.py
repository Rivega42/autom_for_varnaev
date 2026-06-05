"""Проверка init-скрипта БД: расширение timescaledb включается до миграций."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_timescaledb_init_script_present() -> None:
    """В db/init есть скрипт, включающий расширение timescaledb."""
    sql = (REPO_ROOT / "db/init/01_timescaledb.sql").read_text(encoding="utf-8")
    assert "CREATE EXTENSION" in sql
    assert "timescaledb" in sql
