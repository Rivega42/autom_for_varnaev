"""Проверка модели ландмарков и пайплайна pose_v1."""

from video_analytics.detector import PIPELINE
from video_analytics.landmarks import (
    POSE_LANDMARK_COUNT,
    Landmark,
    PoseLandmark,
    PoseResult,
)


def _pose(**overrides: Landmark) -> PoseResult:
    """Собрать PoseResult из 33 нулевых точек с переопределениями по индексу."""
    points = [Landmark(0.0, 0.0, 0.0) for _ in range(POSE_LANDMARK_COUNT)]
    for name, lm in overrides.items():
        points[int(PoseLandmark[name])] = lm
    return PoseResult(points)


def test_pipeline_name() -> None:
    assert PIPELINE == "pose_v1"


def test_point_access_by_landmark() -> None:
    pose = _pose(RIGHT_WRIST=Landmark(0.4, 0.2, 0.9))
    wrist = pose.point(PoseLandmark.RIGHT_WRIST)
    assert wrist.x == 0.4
    assert wrist.y == 0.2


def test_visibility_check() -> None:
    pose = _pose(LEFT_KNEE=Landmark(0.5, 0.6, 0.3))
    assert pose.visible(PoseLandmark.LEFT_KNEE, threshold=0.5) is False
    assert pose.visible(PoseLandmark.LEFT_KNEE, threshold=0.2) is True
