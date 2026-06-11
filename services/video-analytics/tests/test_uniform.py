"""Проверка эвристики «белого халата»."""

from datetime import UTC, datetime, timedelta

import numpy as np
from video_analytics.landmarks import POSE_LANDMARK_COUNT, Landmark, PoseLandmark, PoseResult
from video_analytics.uniform import (
    UniformViolationDetector,
    build_condition_flagged,
    build_uniform_violation,
    is_white_coat,
    mean_brightness_saturation,
    torso_polygon,
)

from monitoring_shared import EventType

_T0 = datetime(2026, 6, 6, 10, 0, tzinfo=UTC)

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


def test_build_uniform_violation() -> None:
    event = build_uniform_violation(7.0, 0.4, 0.5, "room-01", _T0)
    assert event.type is EventType.UNIFORM_VIOLATION
    assert event.payload["flag"] == "no_uniform"
    assert event.payload["duration_s"] == 7.0


def test_detector_fires_once_after_threshold() -> None:
    """Нет халата дольше порога → длительность один раз, затем тишина."""
    det = UniformViolationDetector(min_seconds=5.0)
    assert det.update(has_uniform=False, ts=_T0) is None  # старт эпизода
    assert det.update(False, _T0 + timedelta(seconds=3)) is None  # ещё рано
    fired = det.update(False, _T0 + timedelta(seconds=6))
    assert fired is not None and fired >= 5.0
    assert det.update(False, _T0 + timedelta(seconds=9)) is None  # повтора нет


def test_detector_resets_when_uniform_returns() -> None:
    """Возврат халата сбрасывает эпизод — новое нарушение фиксируется снова."""
    det = UniformViolationDetector(min_seconds=5.0)
    det.update(False, _T0)
    assert det.update(False, _T0 + timedelta(seconds=6)) is not None
    det.update(has_uniform=True, ts=_T0 + timedelta(seconds=7))  # халат вернулся
    det.update(False, _T0 + timedelta(seconds=8))  # новый эпизод
    assert det.update(False, _T0 + timedelta(seconds=14)) is not None


def test_detector_no_fire_below_threshold() -> None:
    """Короткое отсутствие халата (меньше порога) не фиксируется."""
    det = UniformViolationDetector(min_seconds=5.0)
    det.update(False, _T0)
    assert det.update(False, _T0 + timedelta(seconds=2)) is None
