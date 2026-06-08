"""Проверка Dockerfile применения миграций (db/Dockerfile): slim, non-root, alembic."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = REPO_ROOT / "db/Dockerfile"


def _content() -> str:
    return _DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_exists() -> None:
    """Dockerfile миграций существует."""
    assert _DOCKERFILE.is_file()


def test_slim_base() -> None:
    """Образ на slim-базе python:3.12."""
    froms = [line for line in _content().splitlines() if line.strip().startswith("FROM ")]
    assert froms, "Нет инструкции FROM"
    assert all("python:3.12-slim" in line for line in froms)


def test_non_root_user() -> None:
    """Миграции выполняются под непривилегированным пользователем."""
    content = _content()
    assert "USER appuser" in content
    assert "useradd" in content


def test_copies_migrations_and_config() -> None:
    """В образ копируются alembic.ini и каталог миграций."""
    content = _content()
    assert "alembic.ini" in content
    assert "db/migrations" in content


def test_cmd_runs_alembic_upgrade_head() -> None:
    """CMD приводит схему к последней ревизии (alembic upgrade head)."""
    content = _content()
    assert "alembic" in content
    assert "upgrade" in content
    assert "head" in content
