"""Составные действия (порт PoC §2.2): протирание, хлопок, ходьба на месте.

Скользящее окно: подсчёт разворотов движения по горизонтали (протирание),
сближение запястий (хлопок), чередование колен (ходьба). На завершении —
событие action_detected с длительностью.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from monitoring_shared import Event, EventSource, EventType, Severity
from video_analytics.landmarks import PoseLandmark, PoseResult


@dataclass(frozen=True)
class ActionDetection:
    """Распознанное составное действие."""

    action: str
    hands: str | None
    duration_s: float
    message: str


class ReversalCounter:
    """Счётчик разворотов движения координаты по горизонтали (с порогом шума)."""

    def __init__(self, min_amplitude: float = 0.02) -> None:
        self.count = 0
        self._dir = 0
        self._x: float | None = None

    def update(self, x: float) -> None:
        if self._x is None:
            self._x = x
            return
        dx = x - self._x
        if abs(dx) < 0.02:
            return
        direction = 1 if dx > 0 else -1
        if self._dir != 0 and direction != self._dir:
            self.count += 1
        self._dir = direction
        self._x = x


def _point_in_polygon(x: float, y: float, poly: Sequence[Sequence[float]]) -> bool:
    """Тест «точка внутри полигона» (ray casting); poly — вершины [x, y]."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _wrist_in_any(
    pose: PoseResult, landmark: PoseLandmark, polygons: Sequence[Sequence[Sequence[float]]]
) -> bool:
    """Кисть внутри хотя бы одного полигона. Пустой список — True (без гейтинга)."""
    if not polygons:
        return True
    p = pose.point(landmark)
    return any(_point_in_polygon(p.x, p.y, poly) for poly in polygons)


class WipingDetector:
    """Протирание поверхности: одна или обе руки делают >= needed разворотов.

    Развороты руки считаются только пока её кисть «в зоне» (left_in_zone/
    right_in_zone) — порт PoC §2.1 (руки в зоне «стол»). Две руки → событие
    «двумя руками»; одна (вторая бездействует) → одноручное.
    """

    def __init__(self, needed: int = 3) -> None:
        self._needed = needed
        self._left = ReversalCounter()
        self._right = ReversalCounter()
        self._start: datetime | None = None
        self._fired = False

    def update(
        self,
        pose: PoseResult,
        ts: datetime,
        *,
        left_in_zone: bool = True,
        right_in_zone: bool = True,
    ) -> ActionDetection | None:
        if self._start is None:
            self._start = ts
        if left_in_zone:
            self._left.update(pose.point(PoseLandmark.LEFT_WRIST).x)
        if right_in_zone:
            self._right.update(pose.point(PoseLandmark.RIGHT_WRIST).x)
        if self._fired:
            return None
        left, right, need = self._left.count, self._right.count, self._needed
        seconds = (ts - self._start).total_seconds()
        if left >= need and right >= need:
            hands, msg = "both", f"Протирание поверхности двумя руками, {seconds:.0f} с"
        elif left >= need and right == 0:
            hands, msg = "left", f"Протирание поверхности левой рукой, {seconds:.0f} с"
        elif right >= need and left == 0:
            hands, msg = "right", f"Протирание поверхности правой рукой, {seconds:.0f} с"
        else:
            return None
        self._fired = True
        return ActionDetection("surface_wiped", hands, seconds, msg)


class ClapDetector:
    """Хлопок: запястья были разведены и резко сблизились."""

    def __init__(self, near: float = 0.08, far: float = 0.25) -> None:
        self._near = near
        self._far = far
        self._was_far = False

    def update(self, pose: PoseResult, ts: datetime) -> ActionDetection | None:
        lw = pose.point(PoseLandmark.LEFT_WRIST)
        rw = pose.point(PoseLandmark.RIGHT_WRIST)
        dist = math.hypot(lw.x - rw.x, lw.y - rw.y)
        if dist >= self._far:
            self._was_far = True
        elif dist <= self._near and self._was_far:
            self._was_far = False
            return ActionDetection("clap", "both", 0.0, "Хлопок в ладоши")
        return None


class WalkingDetector:
    """Ходьба на месте: чередование поднятий левого/правого колена."""

    def __init__(self, needed: int = 4, raise_margin: float = 0.03) -> None:
        self._needed = needed
        self._margin = raise_margin
        self._alternations = 0
        self._last_up: str | None = None
        self._start: datetime | None = None
        self._fired = False

    def update(self, pose: PoseResult, ts: datetime) -> ActionDetection | None:
        if self._start is None:
            self._start = ts
        left_up = (
            pose.point(PoseLandmark.LEFT_HIP).y - pose.point(PoseLandmark.LEFT_KNEE).y
            > self._margin
        )
        right_up = (
            pose.point(PoseLandmark.RIGHT_HIP).y - pose.point(PoseLandmark.RIGHT_KNEE).y
            > self._margin
        )
        current = "left" if left_up else "right" if right_up else None
        if current is not None and current != self._last_up:
            if self._last_up is not None:
                self._alternations += 1
            self._last_up = current
        if not self._fired and self._alternations >= self._needed:
            self._fired = True
            seconds = (ts - self._start).total_seconds()
            return ActionDetection("walking", None, seconds, f"Ходьба на месте, {seconds:.0f} с")
        return None


class CompositeActionAnalyzer:
    """Агрегатор детекторов составных действий."""

    def __init__(self) -> None:
        self._wiping = WipingDetector()
        self._clap = ClapDetector()
        self._walking = WalkingDetector()

    def process(
        self,
        pose: PoseResult,
        ts: datetime,
        table_polygons: Sequence[Sequence[Sequence[float]]] = (),
    ) -> list[ActionDetection]:
        """Прогнать кадр через детекторы действий.

        `table_polygons` — полигоны ROI-зон «стол» (нормированные). Если заданы,
        протирание засчитывается только когда кисть в зоне «стол» (PoC §2.1).
        Пусто — гейтинга нет (легаси-поведение).
        """
        detections: list[ActionDetection] = []
        left_in = _wrist_in_any(pose, PoseLandmark.LEFT_WRIST, table_polygons)
        right_in = _wrist_in_any(pose, PoseLandmark.RIGHT_WRIST, table_polygons)
        wipe = self._wiping.update(pose, ts, left_in_zone=left_in, right_in_zone=right_in)
        if wipe is not None:
            detections.append(wipe)
        for detector in (self._clap, self._walking):
            result = detector.update(pose, ts)
            if result is not None:
                detections.append(result)
        return detections


def build_action_event(detection: ActionDetection, room_id: str | None, ts: datetime) -> Event:
    """Сформировать событие action_detected."""
    payload: dict[str, object] = {"action": detection.action, "duration_s": detection.duration_s}
    if detection.hands is not None:
        payload["hands"] = detection.hands
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.ACTION_DETECTED,
        room_id=room_id,
        severity=Severity.INFO,
        message=detection.message,
        payload=payload,
    )
