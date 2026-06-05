"""Проверка простых событий поз (гистерезис/антидребезг)."""

from datetime import UTC, datetime

from video_analytics.landmarks import (
    POSE_LANDMARK_COUNT,
    Landmark,
    PoseLandmark,
    PoseResult,
)
from video_analytics.pose_events import (
    Edge,
    HysteresisFlag,
    PoseDetection,
    SimplePoseAnalyzer,
    build_pose_event,
)

from monitoring_shared import EventType


def _pose(right_wrist_y: float) -> PoseResult:
    points = [Landmark(0.5, 0.5, 0.9) for _ in range(POSE_LANDMARK_COUNT)]
    points[int(PoseLandmark.RIGHT_SHOULDER)] = Landmark(0.5, 0.5, 0.9)
    points[int(PoseLandmark.RIGHT_WRIST)] = Landmark(0.5, right_wrist_y, 0.9)
    return PoseResult(points)


def test_hysteresis_flag_debounce() -> None:
    flag = HysteresisFlag(enter=0.05, exit_=0.0, debounce=2)
    assert flag.update(0.1) is None  # 1-й кадр выше — ещё рано
    assert flag.update(0.1) is Edge.RISING  # 2-й — срабатывание
    assert flag.update(0.1) is None
    assert flag.update(-0.1) is None
    assert flag.update(-0.1) is Edge.FALLING


def test_analyzer_detects_right_arm_up_once() -> None:
    analyzer = SimplePoseAnalyzer(debounce=2)
    # рука внизу (запястье ниже плеча: y больше)
    analyzer.process(_pose(0.8))
    analyzer.process(_pose(0.8))
    # рука поднята (запястье выше плеча: y меньше) — нужно 2 кадра
    first = analyzer.process(_pose(0.2))
    second = analyzer.process(_pose(0.2))
    assert first == []
    assert [d.pose for d in second] == ["right_arm_up"]


def test_build_pose_event() -> None:
    event = build_pose_event(
        PoseDetection("right_arm_up", "right_arm", "Поднята правая рука"),
        "room-01",
        datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
    )
    assert event.type is EventType.POSE_EVENT
    assert event.message == "Поднята правая рука"
    assert event.payload["limb"] == "right_arm"
