"""Проверка release-Dockerfile video-analytics (E9.3): Nuitka компилирует наш код."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = REPO_ROOT / "services/video-analytics/Dockerfile.release"


def _content() -> str:
    return _DOCKERFILE.read_text(encoding="utf-8")


def test_release_dockerfile_exists() -> None:
    """Release-Dockerfile сервиса существует."""
    assert _DOCKERFILE.is_file()


def test_compiles_our_packages_via_nuitka_module() -> None:
    """Nuitka компилирует наши пакеты в module-режиме (.so), а не сторонние."""
    content = _content()
    assert "nuitka --module video_analytics" in content
    assert "nuitka --module monitoring_shared" in content


def test_strips_our_python_sources() -> None:
    """Исходники нашей логики (.py) удаляются из site-packages."""
    content = _content()
    assert "-name '*.py' -delete" in content
    assert "video_analytics" in content


def test_runtime_non_root() -> None:
    """Финальный образ работает под непривилегированным пользователем."""
    content = _content()
    assert "USER appuser" in content
    assert "useradd" in content


def test_cmd_runs_compiled_worker() -> None:
    """CMD запускает воркер (через лаунчер скомпилированного кода)."""
    assert "run.py" in _content()
