"""Проверка, что CI инспектирует состав release-образа (E9.5).

Сам состав образа проверяется шагом в workflow release-build (на реально
собранном образе). Здесь — валидация, что эта проверка присутствует и не
была случайно удалена (как в других тестах CI-конфигурации).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = REPO_ROOT / ".github/workflows/release-build.yml"


def _steps() -> list[dict[str, Any]]:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["release-build"]["steps"]
    assert isinstance(steps, list)
    return steps


def test_image_loaded_for_inspection() -> None:
    """Образ загружается в docker (load: true) — иначе нечего инспектировать."""
    build = next(s for s in _steps() if "build-push-action" in str(s.get("uses", "")))
    assert build["with"]["load"] is True


def test_composition_check_present() -> None:
    """Есть шаг проверки состава: нет .py нашей логики и нет шелла у distroless."""
    runs = "\n".join(str(s.get("run", "")) for s in _steps())
    assert ".py" in runs, "Нет проверки на отсутствие .py нашей логики"
    assert "bin/sh" in runs, "Нет проверки на отсутствие шелла"
    assert "video_analytics" in runs
    assert "api_gateway" in runs
