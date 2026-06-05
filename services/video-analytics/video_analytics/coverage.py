"""ROI-зоны и расчёт % покрытия (порт PoC §2.3).

Покрытие считается по heat-маске движения, наложенной на полигон зоны:
доля площади полигона, реально «закрашенная» движением. Геометрия — на
чистом numpy (без cv2), чтобы тестировать без тяжёлых зависимостей.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from monitoring_shared import Event, EventSource, EventType, Severity

BoolMask = NDArray[np.bool_]


def _point_in_polygon(x: float, y: float, poly: Sequence[tuple[float, float]]) -> bool:
    """Тест «точка внутри полигона» методом трассировки луча (even-odd)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygon_mask(height: int, width: int, polygon_norm: Sequence[Sequence[float]]) -> BoolMask:
    """Построить булеву маску полигона по нормированным вершинам [0..1]."""
    poly = [(px * width, py * height) for px, py in polygon_norm]
    mask: BoolMask = np.zeros((height, width), dtype=np.bool_)
    for yy in range(height):
        for xx in range(width):
            if _point_in_polygon(xx + 0.5, yy + 0.5, poly):
                mask[yy, xx] = True
    return mask


def coverage_pct(heat: BoolMask, poly_mask: BoolMask) -> float:
    """Доля площади полигона, закрытая heat-маской, в процентах."""
    total = int(poly_mask.sum())
    if total == 0:
        return 0.0
    covered = int(np.logical_and(heat, poly_mask).sum())
    return covered / total * 100.0


def zone_coverage_pct(heat: BoolMask, polygon_norm: Sequence[Sequence[float]]) -> float:
    """% покрытия зоны (полигон в нормированных координатах) heat-маской."""
    height, width = heat.shape
    return coverage_pct(heat, polygon_mask(height, width, polygon_norm))


def build_coverage_event(
    zone_type: str,
    zone_id: int,
    coverage: float,
    room_id: str | None,
    ts: datetime,
) -> Event:
    """Сформировать событие coverage_report."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.COVERAGE_REPORT,
        room_id=room_id,
        severity=Severity.INFO,
        message=f"Покрытие зоны «{zone_type}» — {coverage:.0f}%",
        payload={"zone": zone_type, "zone_id": zone_id, "coverage_pct": round(coverage)},
    )
