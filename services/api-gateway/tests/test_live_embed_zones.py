"""Разметка ROI-зон в нативном «Живом анализе» (#256): смоук по live-embed.mjs.

Логика рисования — браузерная (canvas/pointer-события), юнит-тестами её не
покрыть; здесь — стражи, что редактор зон присутствует и говорит с API
правильными путями (создание/перетаскивание/удаление + живое обновление ядра).
"""

from __future__ import annotations

from pathlib import Path

_EMBED = (
    Path(__file__).resolve().parents[1] / "api_gateway" / "static" / "live-embed.mjs"
).read_text(encoding="utf-8")


def test_zone_editor_present() -> None:
    """В компоненте есть режим разметки: кнопка, слой и pointer-обработчики."""
    assert "Зоны ✎" in _EMBED
    assert 'addEventListener("pointerdown"' in _EMBED
    assert 'addEventListener("pointermove"' in _EMBED
    assert 'addEventListener("pointerup"' in _EMBED


def test_zone_editor_talks_to_api() -> None:
    """Создание — POST зон камеры; правка углов — PATCH; удаление — DELETE."""
    assert '`/cameras/${cameraId}/zones`, "POST"' in _EMBED
    assert '"PATCH", { polygon' in _EMBED
    assert '"DELETE"' in _EMBED


def test_engine_picks_up_zone_changes_live() -> None:
    """После правок ядро получает свежие зоны без перемонтирования."""
    assert "engine.rois = zonesToRois(liveZones)" in _EMBED


def test_rectangle_has_four_corners_normalized() -> None:
    """Новая зона — прямоугольник из четырёх нормализованных вершин."""
    assert "[[xa, ya], [xb, ya], [xb, yb], [xa, yb]]" in _EMBED
    assert "clamp01" in _EMBED
