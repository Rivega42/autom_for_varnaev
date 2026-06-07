"""Проверка Dockerfile сервиса api-gateway (E9.1): multi-stage, slim, non-root."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = REPO_ROOT / "services/api-gateway/Dockerfile"


def _content() -> str:
    return _DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_exists() -> None:
    """Dockerfile сервиса существует."""
    assert _DOCKERFILE.is_file()


def test_multi_stage_slim_base() -> None:
    """Образ multi-stage (две стадии) на slim-базе python:3.12."""
    froms = [line for line in _content().splitlines() if line.strip().startswith("FROM ")]
    assert len(froms) >= 2, "Ожидаются как минимум две стадии (builder + runtime)"
    assert all("python:3.12-slim" in line for line in froms)


def test_non_root_user() -> None:
    """Финальный образ работает под непривилегированным пользователем."""
    content = _content()
    assert "USER appuser" in content
    assert "useradd" in content


def test_cmd_runs_asgi_app() -> None:
    """CMD запускает ASGI-приложение api_gateway.app:app через uvicorn."""
    content = _content()
    assert "uvicorn" in content
    assert "api_gateway.app:app" in content
