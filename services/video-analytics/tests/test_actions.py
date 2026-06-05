"""Проверка составных действий."""

from datetime import UTC, datetime, timedelta

from video_analytics.actions import (
    ClapDetector,
    CompositeActionAnalyzer,
    WalkingDetector,
    WipingDetector,
    build_action_event,
)
from video_analytics.landmarks import POSE_LANDMARK_COUNT, Landmark, PoseLandmark, PoseResult

from monitoring_shared import EventType

_T0 = datetime(2026, 6, 5, 10, 0, tzinfo=UTC)


def _pose(**pts: Landmark) -> PoseResult:
    points = [Landmark(0.5, 0.5, 0.9) for _ in range(POSE_LANDMARK_COUNT)]
    for name, lm in pts.items():
        points[int(PoseLandmark[name])] = lm
    return PoseResult(points)


def test_wiping_two_hands() -> None:
    det = WipingDetector(needed=3)
    xs = [0.3, 0.6, 0.3, 0.6, 0.3, 0.6, 0.3, 0.6]
    result = None
    for i, x in enumerate(xs):
        pose = _pose(LEFT_WRIST=Landmark(x, 0.5, 0.9), RIGHT_WRIST=Landmark(x, 0.5, 0.9))
        r = det.update(pose, _T0 + timedelta(seconds=i * 0.2))
        result = result or r
    assert result is not None
    assert result.action == "surface_wiped"
    assert result.hands == "both"


def test_clap() -> None:
    det = ClapDetector()
    apart = _pose(LEFT_WRIST=Landmark(0.2, 0.5, 0.9), RIGHT_WRIST=Landmark(0.8, 0.5, 0.9))
    together = _pose(LEFT_WRIST=Landmark(0.49, 0.5, 0.9), RIGHT_WRIST=Landmark(0.51, 0.5, 0.9))
    assert det.update(apart, _T0) is None
    result = det.update(together, _T0 + timedelta(seconds=0.2))
    assert result is not None
    assert result.action == "clap"


def test_walking() -> None:
    det = WalkingDetector(needed=4)
    up_left = _pose(LEFT_KNEE=Landmark(0.5, 0.2, 0.9), LEFT_HIP=Landmark(0.5, 0.5, 0.9))
    up_right = _pose(RIGHT_KNEE=Landmark(0.5, 0.2, 0.9), RIGHT_HIP=Landmark(0.5, 0.5, 0.9))
    result = None
    for i in range(8):
        pose = up_left if i % 2 == 0 else up_right
        r = det.update(pose, _T0 + timedelta(seconds=i * 0.3))
        result = result or r
    assert result is not None
    assert result.action == "walking"


def test_build_action_event() -> None:
    analyzer = CompositeActionAnalyzer()
    assert isinstance(analyzer, CompositeActionAnalyzer)
    from video_analytics.actions import ActionDetection

    event = build_action_event(
        ActionDetection("surface_wiped", "both", 4.0, "Протирание поверхности двумя руками, 4 с"),
        "room-01",
        _T0,
    )
    assert event.type is EventType.ACTION_DETECTED
    assert event.payload["hands"] == "both"
    assert event.payload["duration_s"] == 4.0
