"""Проверка проводки эвристики «белого халата» в воркере (uniform_violation, #272)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import Landmark, PoseLandmark, PoseResult
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, metadata
from video_analytics.worker import run_once

from monitoring_shared import EventType, SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings() -> Settings:
    return Settings(log_service_url="http://log-service:8000", artifacts_dir="/tmp", fps=5)


def _insert_task(engine: Engine) -> UUID:
    task_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=task_id,
                created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
                source_type=SourceType.FILE.value,
                source_ref="/data/clip.mp4",
                room_id="room-01",
                pipeline="pose_v1",
                status=TaskStatus.QUEUED.value,
                trigger=TaskTrigger.SCHEDULE.value,
            )
        )
    return task_id


def _pose_with_torso() -> PoseResult:
    """Поза с видимым четырёхугольником торса (плечи и бёдра)."""
    lms = [Landmark(0.5, 0.5, 1.0) for _ in range(33)]
    lms[int(PoseLandmark.LEFT_SHOULDER)] = Landmark(0.3, 0.3, 1.0)
    lms[int(PoseLandmark.RIGHT_SHOULDER)] = Landmark(0.7, 0.3, 1.0)
    lms[int(PoseLandmark.RIGHT_HIP)] = Landmark(0.7, 0.7, 1.0)
    lms[int(PoseLandmark.LEFT_HIP)] = Landmark(0.3, 0.7, 1.0)
    return PoseResult(lms)


class _FakeDetector:
    def __init__(self, pose: PoseResult) -> None:
        self._pose = pose

    def detect(self, frame: Frame) -> PoseResult | None:
        return self._pose


def _clock(step_s: float = 1.0) -> Callable[[], datetime]:
    """Часы, продвигающиеся на step_s секунд за каждый вызов (для накопления длительности)."""
    state = {"t": datetime(2026, 6, 6, 10, 0, tzinfo=UTC)}

    def now() -> datetime:
        cur = state["t"]
        state["t"] = cur + timedelta(seconds=step_s)
        return cur

    return now


def _run(engine: Engine, frame: Frame, frames: int = 10) -> CollectingEventSink:
    sink = CollectingEventSink()
    source: FrameSource = FakeFrameSource([frame] * frames)
    run_once(
        engine,
        _settings(),
        detector=_FakeDetector(_pose_with_torso()),
        sink=sink,
        source_factory=lambda *_: source,
        save_frame=lambda *_: None,  # не трогаем cv2 в тестах
        now_fn=_clock(),  # время идёт — иначе длительность нарушения не накопится
    )
    return sink


def test_dark_clothing_long_enough_triggers_violation() -> None:
    """Тёмная одежда на торсе дольше порога → событие uniform_violation."""
    engine = _engine()
    _insert_task(engine)
    frame: Frame = np.full((100, 100, 3), 30, dtype=np.uint8)
    sink = _run(engine, frame)
    violations = [e for e in sink.events if e.type is EventType.UNIFORM_VIOLATION]
    assert len(violations) == 1  # раз на эпизод
    assert violations[0].payload["flag"] == "no_uniform"


def test_white_coat_no_violation() -> None:
    """Белый халат (яркий, ненасыщенный торс) → нарушения нет."""
    engine = _engine()
    _insert_task(engine)
    frame: Frame = np.full((100, 100, 3), 240, dtype=np.uint8)
    sink = _run(engine, frame)
    assert not any(e.type is EventType.UNIFORM_VIOLATION for e in sink.events)


def test_short_violation_below_threshold_no_event() -> None:
    """Короткое отсутствие халата (меньше порога) события не даёт."""
    engine = _engine()
    _insert_task(engine)
    frame: Frame = np.full((100, 100, 3), 30, dtype=np.uint8)
    # 3 кадра по 1 c < порога 5 c → нарушение не фиксируется
    sink = _run(engine, frame, frames=3)
    assert not any(e.type is EventType.UNIFORM_VIOLATION for e in sink.events)
