"""Простые события поз (порт PoC §2.1): пороги с гистерезисом и антидребезгом.

Детекторы считают скалярную величину по ландмаркам; флаг с гистерезисом
(разные пороги входа/выхода) и антидребезгом (N кадров) даёт фронты. На
переднем фронте формируется событие pose_event.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto
from uuid import uuid4

from monitoring_shared import Event, EventSource, EventType, Severity
from video_analytics.landmarks import PoseLandmark, PoseResult


class Edge(StrEnum):
    """Фронт изменения состояния флага."""

    RISING = auto()
    FALLING = auto()


class HysteresisFlag:
    """Булев флаг с гистерезисом (enter/exit) и антидребезгом (debounce кадров)."""

    def __init__(self, enter: float, exit_: float, debounce: int = 2) -> None:
        self.active = False
        self._enter = enter
        self._exit = exit_
        self._debounce = debounce
        self._count = 0

    def update(self, value: float) -> Edge | None:
        """Обновить флаг значением; вернуть фронт (RISING/FALLING) или None."""
        target = value >= self._enter if not self.active else value > self._exit
        if target != self.active:
            self._count += 1
            if self._count >= self._debounce:
                self.active = target
                self._count = 0
                return Edge.RISING if target else Edge.FALLING
        else:
            self._count = 0
        return None


@dataclass(frozen=True)
class PoseSpec:
    """Описание простой позы: имя, конечность, точки, функция величины, сообщение."""

    pose: str
    limb: str
    message: str
    required: tuple[PoseLandmark, ...]
    value: Callable[[PoseResult], float]


# y растёт вниз: «выше» = меньшая y. value > 0 — конечность поднята.
_POSES: tuple[PoseSpec, ...] = (
    PoseSpec(
        "right_arm_up",
        "right_arm",
        "Поднята правая рука",
        (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_WRIST),
        lambda p: p.point(PoseLandmark.RIGHT_SHOULDER).y - p.point(PoseLandmark.RIGHT_WRIST).y,
    ),
    PoseSpec(
        "left_arm_up",
        "left_arm",
        "Поднята левая рука",
        (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_WRIST),
        lambda p: p.point(PoseLandmark.LEFT_SHOULDER).y - p.point(PoseLandmark.LEFT_WRIST).y,
    ),
    PoseSpec(
        "right_knee_up",
        "right_knee",
        "Поднято правое колено",
        (PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE),
        lambda p: p.point(PoseLandmark.RIGHT_HIP).y - p.point(PoseLandmark.RIGHT_KNEE).y,
    ),
    PoseSpec(
        "left_knee_up",
        "left_knee",
        "Поднято левое колено",
        (PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE),
        lambda p: p.point(PoseLandmark.LEFT_HIP).y - p.point(PoseLandmark.LEFT_KNEE).y,
    ),
)


@dataclass(frozen=True)
class PoseDetection:
    """Распознанная простая поза (передний фронт)."""

    pose: str
    limb: str
    message: str


class SimplePoseAnalyzer:
    """Отслеживает простые позы по кадрам с гистерезисом/антидребезгом."""

    def __init__(self, enter: float = 0.05, exit_: float = 0.0, debounce: int = 2) -> None:
        self._flags = {spec.pose: HysteresisFlag(enter, exit_, debounce) for spec in _POSES}

    def process(self, pose: PoseResult) -> list[PoseDetection]:
        """Обработать кадр; вернуть события поз на переднем фронте."""
        detections: list[PoseDetection] = []
        for spec in _POSES:
            if not all(pose.visible(lm) for lm in spec.required):
                continue
            edge = self._flags[spec.pose].update(spec.value(pose))
            if edge is Edge.RISING:
                detections.append(PoseDetection(spec.pose, spec.limb, spec.message))
        return detections


def build_pose_event(detection: PoseDetection, room_id: str | None, ts: datetime) -> Event:
    """Сформировать событие pose_event из распознанной позы."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.POSE_EVENT,
        room_id=room_id,
        severity=Severity.INFO,
        message=detection.message,
        payload={"pose": detection.pose, "limb": detection.limb},
    )
