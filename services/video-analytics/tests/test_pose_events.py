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


def _build(coords: dict[PoseLandmark, tuple[float, float]]) -> PoseResult:
    """Поза: все точки в центре (0.5,0.5), кроме заданных в coords."""
    pts = [Landmark(0.5, 0.5, 0.9) for _ in range(POSE_LANDMARK_COUNT)]
    for lm, (x, y) in coords.items():
        pts[int(lm)] = Landmark(x, y, 0.9)
    return PoseResult(pts)


def _settle(analyzer: SimplePoseAnalyzer, pose: PoseResult, frames: int = 2) -> list[str]:
    """Прогнать позу `frames` кадров; вернуть имена поз последнего кадра."""
    last: list[PoseDetection] = []
    for _ in range(frames):
        last = analyzer.process(pose)
    return [d.pose for d in last]


def test_both_arms_up() -> None:
    """Подняты обе руки — обе кисти выше плеч."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    pose = _build({PoseLandmark.RIGHT_WRIST: (0.5, 0.2), PoseLandmark.LEFT_WRIST: (0.5, 0.2)})
    assert "both_arms_up" in _settle(analyzer, pose)


def test_arm_lowered_emits_falling() -> None:
    """После поднятия и опускания руки эмитится «опущена рука» (задний фронт)."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    _settle(analyzer, _build({PoseLandmark.RIGHT_WRIST: (0.5, 0.2)}))  # рука вверх
    down = _settle(analyzer, _build({PoseLandmark.RIGHT_WRIST: (0.5, 0.8)}))  # вниз
    assert "right_arm_down" in down


def test_head_turn_right() -> None:
    """Нос смещён вправо от середины плеч — поворот головы вправо."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    poses = _settle(analyzer, _build({PoseLandmark.NOSE: (0.62, 0.5)}))
    assert "head_turn_right" in poses
    assert "head_turn_left" not in poses


def test_torso_lean_right() -> None:
    """Плечи смещены вправо относительно бёдер — наклон корпуса вправо."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    pose = _build(
        {
            PoseLandmark.LEFT_SHOULDER: (0.6, 0.5),
            PoseLandmark.RIGHT_SHOULDER: (0.6, 0.5),
            PoseLandmark.NOSE: (0.6, 0.5),  # голова с корпусом — чтобы не считать поворот
        }
    )
    assert "torso_lean_right" in _settle(analyzer, pose)


def test_squat() -> None:
    """Колени близко к бёдрам (бедро «сжато») — приседание."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    pose = _build(
        {
            PoseLandmark.LEFT_SHOULDER: (0.5, 0.3),
            PoseLandmark.RIGHT_SHOULDER: (0.5, 0.3),
            PoseLandmark.LEFT_HIP: (0.5, 0.5),
            PoseLandmark.RIGHT_HIP: (0.5, 0.5),
            PoseLandmark.LEFT_KNEE: (0.5, 0.55),
            PoseLandmark.RIGHT_KNEE: (0.5, 0.55),
        }
    )
    assert "squat" in _settle(analyzer, pose)


def test_neutral_pose_no_detections() -> None:
    """Нейтральная поза (всё в центре) не порождает событий."""
    analyzer = SimplePoseAnalyzer(debounce=2)
    assert _settle(analyzer, _build({})) == []


def test_build_pose_event() -> None:
    event = build_pose_event(
        PoseDetection("right_arm_up", "right_arm", "Поднята правая рука"),
        "room-01",
        datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
    )
    assert event.type is EventType.POSE_EVENT
    assert event.message == "Поднята правая рука"
    assert event.payload["limb"] == "right_arm"
