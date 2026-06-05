"""Составные действия (порт PoC §2.2): протирание, хлопок, ходьба на месте.

Скользящее окно: подсчёт разворотов движения по горизонтали (протирание),
сближение запястий (хлопок), чередование колен (ходьба). На завершении —
событие action_detected с длительностью.
"""

from __future__ import annotations

import math
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


class WipingDetector:
    """Протирание двумя руками: обе руки делают >= needed разворотов."""

    def __init__(self, needed: int = 3) -> None:
        self._needed = needed
        self._left = ReversalCounter()
        self._right = ReversalCounter()
        self._start: datetime | None = None
        self._fired = False

    def update(self, pose: PoseResult, ts: datetime) -> ActionDetection | None:
        if self._start is None:
            self._start = ts
        self._left.update(pose.point(PoseLandmark.LEFT_WRIST).x)
        self._right.update(pose.point(PoseLandmark.RIGHT_WRIST).x)
        if (
            not self._fired
            and self._left.count >= self._needed
            and self._right.count >= self._needed
        ):
            self._fired = True
            seconds = (ts - self._start).total_seconds()
            return ActionDetection(
                "surface_wiped",
                "both",
                seconds,
                f"Протирание поверхности двумя руками, {seconds:.0f} с",
            )
        return None


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

    def process(self, pose: PoseResult, ts: datetime) -> list[ActionDetection]:
        detections: list[ActionDetection] = []
        for detector in (self._wiping, self._clap, self._walking):
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
