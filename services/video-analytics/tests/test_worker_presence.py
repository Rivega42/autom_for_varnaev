"""Проверка проводки запретных зон в воркере (#299): forbidden_zone_entry."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import POSE_LANDMARK_COUNT, Landmark, PoseLandmark, PoseResult
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, camera_zones, metadata
from video_analytics.worker import run_once

from monitoring_shared import EventType, SourceType, TaskStatus, TaskTrigger

_FORBIDDEN = [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]]


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings() -> Settings:
    return Settings(log_service_url="http://log-service:8000", artifacts_dir="/tmp", fps=5)


def _insert_task(engine: Engine, camera_id: UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=uuid4(),
                created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
                source_type=SourceType.STREAM.value,
                source_ref="rtsp://media-gateway/room-01",
                room_id="room-01",
                camera_id=camera_id,
                pipeline="pose_v1",
                status=TaskStatus.QUEUED.value,
                trigger=TaskTrigger.SCHEDULE.value,
            )
        )
        conn.execute(
            camera_zones.insert().values(
                id=1, camera_id=camera_id, zone_type="forbidden", polygon=_FORBIDDEN
            )
        )


def _pose(hip_x: float, hip_y: float) -> PoseResult:
    pts = [Landmark(0.0, 0.0, 0.0) for _ in range(POSE_LANDMARK_COUNT)]
    pts[int(PoseLandmark.LEFT_HIP)] = Landmark(hip_x, hip_y, 0.9)
    pts[int(PoseLandmark.RIGHT_HIP)] = Landmark(hip_x, hip_y, 0.9)
    return PoseResult(pts)


class _FixedDetector:
    def __init__(self, pose: PoseResult) -> None:
        self._pose = pose

    def detect(self, frame: Frame) -> PoseResult:
        return self._pose


def _run(engine: Engine, pose: PoseResult, frames: int = 3) -> CollectingEventSink:
    sink = CollectingEventSink()
    blank: Frame = np.zeros((10, 10, 3), dtype=np.uint8)
    source: FrameSource = FakeFrameSource([blank] * frames)  # кадры не важны для фикс-позы
    run_once(
        engine,
        _settings(),
        detector=_FixedDetector(pose),
        sink=sink,
        source_factory=lambda *_: source,
        save_frame=lambda *_: None,
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )
    return sink


def test_person_in_forbidden_zone_triggers_event_once() -> None:
    """Человек внутри запретной зоны → одно событие на эпизод."""
    engine = _engine()
    _insert_task(engine, uuid4())
    sink = _run(engine, _pose(0.7, 0.7))  # бёдра внутри запретной зоны
    entries = [e for e in sink.events if e.type is EventType.FORBIDDEN_ZONE_ENTRY]
    assert len(entries) == 1
    assert entries[0].payload["zone_id"] == 1


def test_person_outside_forbidden_zone_no_event() -> None:
    """Человек вне запретной зоны → события нет."""
    engine = _engine()
    _insert_task(engine, uuid4())
    sink = _run(engine, _pose(0.1, 0.1))  # бёдра вне зоны
    assert not any(e.type is EventType.FORBIDDEN_ZONE_ENTRY for e in sink.events)
