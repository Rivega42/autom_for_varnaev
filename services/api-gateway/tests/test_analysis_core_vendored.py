"""Гарантия единого источника движка анализа (#241, Фаза 2).

Браузер (`static/analysis-core.mjs`) и сервер используют ОДНО ядро. Чтобы
браузерная копия не разъехалась с каноном `services/analysis-core/`, держим тест:
файлы должны быть байт-в-байт одинаковы. Если канон поменяли — пересними копию
(`cp services/analysis-core/analysis-core.mjs services/api-gateway/api_gateway/static/`).
"""

from __future__ import annotations

from pathlib import Path

# .../services/api-gateway/tests/<file> → корень репозитория на 4 уровня выше.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANON = _REPO_ROOT / "services" / "analysis-core" / "analysis-core.mjs"
_VENDORED = _REPO_ROOT / "services" / "api-gateway" / "api_gateway" / "static" / "analysis-core.mjs"


def test_browser_core_matches_canonical() -> None:
    """Браузерная копия ядра идентична канону (единый источник истины)."""
    assert _CANON.is_file(), f"нет канона ядра: {_CANON}"
    assert _VENDORED.is_file(), f"нет браузерной копии ядра: {_VENDORED}"
    assert _VENDORED.read_bytes() == _CANON.read_bytes(), (
        "static/analysis-core.mjs разошёлся с services/analysis-core/analysis-core.mjs — "
        "пересними копию (cp ... static/)."
    )
