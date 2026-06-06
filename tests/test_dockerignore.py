"""Проверка корневого .dockerignore (E9.2): контекст сборки — корень репозитория."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _patterns() -> list[str]:
    lines = _DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def test_dockerignore_exists() -> None:
    """Корневой .dockerignore существует (контекст сборки — корень)."""
    assert _DOCKERIGNORE.is_file()


def test_excludes_caches_and_envs() -> None:
    """Исключены кэши, виртуальные окружения и байткод."""
    patterns = _patterns()
    for needed in ("**/__pycache__/", "**/.pytest_cache/", "**/.mypy_cache/", ".venv/"):
        assert needed in patterns, f"Нет правила {needed}"


def test_excludes_tests_and_git() -> None:
    """Исключены тесты и история git."""
    patterns = _patterns()
    assert "**/tests/" in patterns
    assert ".git/" in patterns


def test_keeps_env_example() -> None:
    """.env исключён, но .env.example оставлен (для образов/документации)."""
    patterns = _patterns()
    assert ".env" in patterns
    assert "!.env.example" in patterns
