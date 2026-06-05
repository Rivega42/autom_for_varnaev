"""Модель ландмарков позы (33 точки MediaPipe Pose).

Лево/право — анатомические (относительно человека), как в PoC. Индексы
соответствуют MediaPipe Pose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

POSE_LANDMARK_COUNT = 33


class PoseLandmark(IntEnum):
    """Индексы используемых точек тела (подмножество 33 точек MediaPipe)."""

    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28


@dataclass(frozen=True)
class Landmark:
    """Одна точка тела: нормированные координаты [0..1] и видимость."""

    x: float
    y: float
    visibility: float


@dataclass(frozen=True)
class PoseResult:
    """Результат детекции позы: 33 точки."""

    landmarks: list[Landmark]

    def point(self, index: PoseLandmark) -> Landmark:
        """Точка по индексу."""
        return self.landmarks[int(index)]

    def visible(self, index: PoseLandmark, threshold: float = 0.5) -> bool:
        """Видна ли точка (по порогу visibility) — как visibility-проверка PoC."""
        return self.point(index).visibility >= threshold
