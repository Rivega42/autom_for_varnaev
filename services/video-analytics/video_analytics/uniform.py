"""Эвристика «белого халата» (порт PoC §2.4): цвет торса.

По точкам плеч (11/12) и бёдер (23/24) строится четырёхугольник торса,
внутри него считаются средняя яркость и насыщенность. Белый халат = высокая
яркость + низкая насыщенность. Это индикатор/условие, а не строгий контроль:
путается на белой стене/нержавейке и при пересвете (см. docs/07 §2.4).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from monitoring_shared import Event, EventSource, EventType, Severity
from video_analytics.coverage import polygon_mask
from video_analytics.landmarks import PoseLandmark, PoseResult

Frame = NDArray[np.uint8]


def torso_polygon(pose: PoseResult) -> list[list[float]]:
    """Четырёхугольник торса: плечи (11/12) и бёдра (23/24)."""
    ls = pose.point(PoseLandmark.LEFT_SHOULDER)
    rs = pose.point(PoseLandmark.RIGHT_SHOULDER)
    rh = pose.point(PoseLandmark.RIGHT_HIP)
    lh = pose.point(PoseLandmark.LEFT_HIP)
    return [[ls.x, ls.y], [rs.x, rs.y], [rh.x, rh.y], [lh.x, lh.y]]


def mean_brightness_saturation(
    frame: Frame, polygon_norm: list[list[float]]
) -> tuple[float, float]:
    """Средние яркость (V) и насыщенность (S) пикселей внутри полигона [0..1]."""
    height, width = frame.shape[:2]
    mask = polygon_mask(height, width, polygon_norm)
    pixels = frame[mask].astype(np.float64)
    if pixels.shape[0] == 0:
        return 0.0, 0.0
    channel_max = pixels.max(axis=1)
    channel_min = pixels.min(axis=1)
    brightness = float((channel_max / 255.0).mean())
    saturation = float(
        np.where(channel_max > 0, (channel_max - channel_min) / channel_max, 0.0).mean()
    )
    return brightness, saturation


def is_white_coat(
    brightness: float, saturation: float, bright_thr: float = 0.5, sat_thr: float = 0.35
) -> bool:
    """Белый халат: высокая яркость и низкая насыщенность.

    Пороги подобраны по замерам на реальных роликах объекта (тёплое внутреннее
    освещение): халат давал яркость 0.57–0.68 и насыщенность 0.02–0.26, поэтому
    исходные 0.7/0.25 давали ложные «без халата». Это эвристика, не строгий
    контроль СИЗ (docs/07 §2.4, обучаемый детектор — issue #105).
    """
    return brightness >= bright_thr and saturation <= sat_thr


def build_condition_flagged(
    brightness: float,
    saturation: float,
    room_id: str | None,
    ts: datetime,
) -> Event:
    """Событие «не распознана спецодежда» (флаг no_uniform)."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.CONDITION_FLAGGED,
        room_id=room_id,
        severity=Severity.WARNING,
        message="Не распознана спецодежда (белый халат)",
        payload={
            "flag": "no_uniform",
            "brightness": round(brightness, 2),
            "saturation": round(saturation, 2),
        },
    )


class UniformViolationDetector:
    """Фиксирует отсутствие халата дольше порога — раз на эпизод (#272).

    На каждом кадре с видимым торсом вызывается `update(has_uniform, ts)`. Пока
    халата нет, накапливается время с первого «нет халата»; при превышении порога
    возвращается длительность (один раз), затем тишина до возврата халата. Это
    эвристика, а не обученный детектор СИЗ (ограничения — docs/07 §2.4, issue #105).
    """

    def __init__(self, min_seconds: float) -> None:
        self._min = min_seconds
        self._since: datetime | None = None
        self._fired = False

    def update(self, has_uniform: bool, ts: datetime) -> float | None:
        """Вернуть длительность нарушения при пересечении порога, иначе None."""
        if has_uniform:
            self._since = None
            self._fired = False
            return None
        if self._since is None:
            self._since = ts
            return None
        if self._fired:
            return None
        elapsed = (ts - self._since).total_seconds()
        if elapsed >= self._min:
            self._fired = True
            return elapsed
        return None


def build_uniform_violation(
    duration_s: float,
    brightness: float,
    saturation: float,
    room_id: str | None,
    ts: datetime,
) -> Event:
    """Событие «человек без спецодежды в зоне дольше нормы» (+стоп-кадр, #272)."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.UNIFORM_VIOLATION,
        room_id=room_id,
        severity=Severity.WARNING,
        message=f"Человек без спецодежды (белого халата) дольше {int(duration_s)} с",
        payload={
            "flag": "no_uniform",
            "duration_s": round(duration_s, 1),
            "brightness": round(brightness, 2),
            "saturation": round(saturation, 2),
        },
    )
