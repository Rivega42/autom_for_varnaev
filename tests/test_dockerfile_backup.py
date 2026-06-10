"""Проверка Dockerfile бэкапа (db/Dockerfile.backup): slim, non-root, pg_dump 16."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = REPO_ROOT / "db/Dockerfile.backup"


def _content() -> str:
    return _DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_exists() -> None:
    """Dockerfile бэкапа существует."""
    assert _DOCKERFILE.is_file()


def test_slim_base() -> None:
    """Образ на slim-базе python:3.12."""
    froms = [line for line in _content().splitlines() if line.strip().startswith("FROM ")]
    assert froms, "Нет инструкции FROM"
    assert all("python:3.12-slim" in line for line in froms)


def test_non_root_user() -> None:
    """Бэкап выполняется под непривилегированным пользователем."""
    content = _content()
    assert "USER appuser" in content
    assert "useradd" in content


def test_installs_pg_client_16() -> None:
    """В образ ставится клиент PostgreSQL 16 (pg_dump не старше сервера)."""
    assert "postgresql-client-16" in _content()


def test_copies_backup_script() -> None:
    """В образ копируется скрипт бэкапа и он запускается как ENTRYPOINT."""
    content = _content()
    assert "scripts/backup_db.py" in content
    assert "backup_db.py" in content
    assert "ENTRYPOINT" in content
