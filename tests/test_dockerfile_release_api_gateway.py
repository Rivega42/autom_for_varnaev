"""Проверка release-Dockerfile api-gateway (E9.4): Nuitka, distroless, без .py."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = REPO_ROOT / "services/api-gateway/Dockerfile.release"


def _content() -> str:
    return _DOCKERFILE.read_text(encoding="utf-8")


def test_release_dockerfile_exists() -> None:
    """Release-Dockerfile сервиса существует."""
    assert _DOCKERFILE.is_file()


def test_uses_nuitka() -> None:
    """Сборка идёт через Nuitka (компиляция в нативный бинарь)."""
    assert "nuitka" in _content().lower()


def test_runtime_is_distroless() -> None:
    """Финальная стадия — distroless (без шелла и пакетного менеджера)."""
    froms = [line for line in _content().splitlines() if line.strip().startswith("FROM ")]
    assert any("distroless" in line for line in froms), "Runtime должен быть distroless"


def test_final_stage_has_no_source_copy() -> None:
    """В runtime копируется только скомпилированный дистрибутив (не исходники .py)."""
    content = _content()
    # Единственный COPY в runtime — из builder'а скомпилированный .dist
    assert ".dist" in content
    # Нет копирования пакета с исходниками в runtime-стадию
    assert "COPY shared/" not in content.split("AS runtime")[1]
    assert "api_gateway/" not in content.split("AS runtime")[1]
