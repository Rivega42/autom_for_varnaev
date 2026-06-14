"""scripts/install.sh: подготовка свежей Ubuntu одной командой (#333).

Скрипт ставит хостовые предпосылки (Docker + compose v2, Python 3, git), которых
нет на голой системе; дальше контур поднимается через bootstrap.sh. Тест — страж
содержимого (без запуска apt/docker): нужные шаги на месте и скрипт безопасен.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_INSTALL = REPO_ROOT / "scripts" / "install.sh"


def _text() -> str:
    return _INSTALL.read_text(encoding="utf-8")


def test_install_script_present_and_safe() -> None:
    """install.sh существует, это bash со строгим режимом."""
    assert _INSTALL.is_file()
    text = _text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text


def test_install_script_installs_prerequisites() -> None:
    """Ставит системные предпосылки: Docker (+compose), Python 3, git."""
    text = _text()
    assert "apt-get install" in text
    assert "python3" in text and "git" in text
    assert "get.docker.com" in text  # официальный установщик Docker + плагин compose
    assert "docker compose version" in text  # проверка наличия compose v2


def test_install_script_requires_root_and_guards_os() -> None:
    """Требует root и не пытается работать на не-Debian (нет apt-get)."""
    text = _text()
    assert "id -u" in text  # проверка root
    assert "command -v apt-get" in text  # защита от не-Debian ОС


def test_install_script_points_to_bootstrap() -> None:
    """Подсказывает следующий шаг — bootstrap.sh."""
    assert "scripts/bootstrap.sh" in _text()
