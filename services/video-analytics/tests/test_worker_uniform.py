"""Проверка проводки эвристики «белого халата» в воркере (condition_flagged)."""

from __future__ import annotations

from datetime import UTC, datetime
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


def _run(engine: Engine, frame: Frame) -> CollectingEventSink:
    sink = CollectingEventSink()
    source: FrameSource = FakeFrameSource([frame])
    run_once(
        engine,
        _settings(),
        detector=_FakeDetector(_pose_with_torso()),
        sink=sink,
        source_factory=lambda *_: source,
        now_fn=lambda: datetime(2026, 6, 6, 10, 1, tzinfo=UTC),
        save_frame=lambda *_: None,
    )
    return sink


def test_dark_clothing_flags_no_uniform() -> None:
    """Тёмная одежда на торсе → событие condition_flagged."""
    engine = _engine()
    _insert_task(engine)
    frame: Frame = np.full((100, 100, 3), 30, dtype=np.uint8)
    sink = _run(engine, frame)
    assert any(e.type is EventType.CONDITION_FLAGGED for e in sink.events)


def test_white_coat_no_flag() -> None:
    """Белый халат (яркий, ненасыщенный торс) → события condition_flagged нет."""
    engine = _engine()
    _insert_task(engine)
    frame: Frame = np.full((100, 100, 3), 240, dtype=np.uint8)
    sink = _run(engine, frame)
    assert not any(e.type is EventType.CONDITION_FLAGGED for e in sink.events)
