"""Проверка учёта пофункциональных тумблеров аналитики камеры в воркере (#196)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import Landmark, PoseLandmark, PoseResult
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, cameras, metadata
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


def _seed_camera(engine: Engine, *, enabled: bool, analytics: dict[str, Any] | None) -> UUID:
    camera_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            cameras.insert().values(
                id=camera_id,
                room_id="room-01",
                name="cam-01",
                rtsp_url="rtsp://cam-01/stream",
                enabled=enabled,
                analytics=analytics,
            )
        )
    return camera_id


def _insert_task(engine: Engine, camera_id: UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=uuid4(),
                created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
                source_type=SourceType.STREAM.value,
                source_ref="rtsp://cam-01/stream",
                room_id="room-01",
                camera_id=camera_id,
                pipeline="pose_v1",
                status=TaskStatus.QUEUED.value,
                trigger=TaskTrigger.SCHEDULE.value,
            )
        )


def _pose_right_arm_up() -> PoseResult:
    lms = [Landmark(0.5, 0.5, 1.0) for _ in range(33)]
    lms[int(PoseLandmark.RIGHT_WRIST)] = Landmark(0.5, 0.2, 1.0)
    return PoseResult(lms)


class _Detector:
    def detect(self, frame: Frame) -> PoseResult:
        return _pose_right_arm_up()


def _frames() -> list[Frame]:
    f: Frame = np.zeros((4, 4, 3), dtype=np.uint8)
    return [f, f, f]


def _run(engine: Engine) -> CollectingEventSink:
    sink = CollectingEventSink()
    source: FrameSource = FakeFrameSource(_frames())
    run_once(
        engine,
        _settings(),
        detector=_Detector(),
        sink=sink,
        source_factory=lambda *_: source,
        save_frame=lambda *_: None,
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )
    return sink


def test_pose_off_suppresses_pose_events() -> None:
    """Тумблер pose=false → событий позы нет."""
    engine = _engine()
    cam = _seed_camera(engine, enabled=True, analytics={"pose": False})
    _insert_task(engine, cam)
    sink = _run(engine)
    assert not any(e.type is EventType.POSE_EVENT for e in sink.events)


def test_pose_on_by_default() -> None:
    """Без тумблеров (analytics=None) поза распознаётся (контроль)."""
    engine = _engine()
    cam = _seed_camera(engine, enabled=True, analytics=None)
    _insert_task(engine, cam)
    sink = _run(engine)
    assert any(e.type is EventType.POSE_EVENT for e in sink.events)


def test_disabled_camera_suppresses_all() -> None:
    """Камера enabled=false → никаких событий аналитики."""
    engine = _engine()
    cam = _seed_camera(engine, enabled=False, analytics=None)
    _insert_task(engine, cam)
    sink = _run(engine)
    assert sink.events == []
