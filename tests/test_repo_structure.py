"""Smoke-тест каркаса монорепо.

Проверяет, что обязательные каталоги структуры (docs/01_ARCHITECTURE.md §8)
существуют. Это самый базовый прогон, чтобы pytest и CI имели зелёный старт
ещё до появления прикладного кода.
"""

from pathlib import Path

# Корень репозитория — на два уровня выше этого файла (tests/ -> repo).
REPO_ROOT = Path(__file__).resolve().parents[1]

# Каталоги верхнего уровня, заданные целевой структурой репозитория.
EXPECTED_DIRS = [
    "services/api-gateway",
    "services/ingest-sensors",
    "services/video-analytics",
    "services/scheduler",
    "services/log-service",
    "media-gateway",
    "db",
    "firmware/esphome",
    "grafana",
    "shared",
    "scripts",
    "docs",
]


def test_expected_directories_exist() -> None:
    """Каждый каталог целевой структуры присутствует в репозитории."""
    missing = [d for d in EXPECTED_DIRS if not (REPO_ROOT / d).is_dir()]
    assert not missing, f"Отсутствуют каталоги структуры: {missing}"


def test_reference_poc_present() -> None:
    """Эталонный PoC видеоаналитики на месте (источник логики для порта E4)."""
    poc = REPO_ROOT / "services/video-analytics/reference/motion-log.html"
    assert poc.is_file(), "Не найден эталон services/video-analytics/reference/motion-log.html"
