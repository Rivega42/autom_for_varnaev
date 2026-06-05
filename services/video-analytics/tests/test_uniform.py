"""Проверка эвристики «белого халата»."""

from datetime import UTC, datetime

import numpy as np
from video_analytics.landmarks import POSE_LANDMARK_COUNT, Landmark, PoseLandmark, PoseResult
from video_analytics.uniform import (
    build_condition_flagged,
    is_white_coat,
    mean_brightness_saturation,
    torso_polygon,
)

from monitoring_shared import EventType

_FULL = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


def _pose() -> PoseResult:
    pts = [Landmark(0.5, 0.5, 0.9) for _ in range(POSE_LANDMARK_COUNT)]
    pts[int(PoseLandmark.LEFT_SHOULDER)] = Landmark(0.3, 0.3, 0.9)
    pts[int(PoseLandmark.RIGHT_SHOULDER)] = Landmark(0.7, 0.3, 0.9)
    pts[int(PoseLandmark.RIGHT_HIP)] = Landmark(0.7, 0.7, 0.9)
    pts[int(PoseLandmark.LEFT_HIP)] = Landmark(0.3, 0.7, 0.9)
    return PoseResult(pts)


def test_torso_polygon() -> None:
    poly = torso_polygon(_pose())
    assert len(poly) == 4
    assert poly[0] == [0.3, 0.3]


def test_white_frame_is_coat() -> None:
    white = np.full((8, 8, 3), 255, dtype=np.uint8)
    brightness, saturation = mean_brightness_saturation(white, _FULL)
    assert brightness == 1.0
    assert saturation == 0.0
    assert is_white_coat(brightness, saturation) is True


def test_colored_frame_not_coat() -> None:
    red = np.zeros((8, 8, 3), dtype=np.uint8)
    red[:, :, 2] = 255  # ярко-красный (BGR)
    brightness, saturation = mean_brightness_saturation(red, _FULL)
    assert saturation == 1.0
    assert is_white_coat(brightness, saturation) is False


def test_build_condition_flagged() -> None:
    event = build_condition_flagged(0.4, 0.5, "room-01", datetime(2026, 6, 5, 10, 0, tzinfo=UTC))
    assert event.type is EventType.CONDITION_FLAGGED
    assert event.payload["flag"] == "no_uniform"
