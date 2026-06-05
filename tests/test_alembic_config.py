"""Проверка, что конфигурация Alembic загружается и видит каталог миграций."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_config_loads() -> None:
    """Config читается, ScriptDirectory указывает на каталог миграций."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert script.dir.endswith("migrations")
