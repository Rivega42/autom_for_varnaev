"""Проверка сохранения скриншот-артефакта задания (E4.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import Landmark, PoseLandmark, PoseResult
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, artifacts, metadata
from video_analytics.worker import run_once

from monitoring_shared import ArtifactKind, SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings() -> Settings:
    return Settings(
        log_service_url="http://log-service:8000", artifacts_dir="/data/artifacts", fps=5
    )


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


def _pose_arm_up() -> PoseResult:
    """Поза с поднятой правой рукой (породит событие)."""
    lms = [Landmark(0.5, 0.5, 1.0) for _ in range(33)]
    lms[int(PoseLandmark.RIGHT_WRIST)] = Landmark(0.5, 0.2, 1.0)
    return PoseResult(lms)


def _pose_silent() -> PoseResult:
    """Поза без видимых точек — событий не порождает (видимость 0)."""
    return PoseResult([Landmark(0.5, 0.5, 0.0) for _ in range(33)])


class _FakeDetector:
    def __init__(self, pose: PoseResult) -> None:
        self._pose = pose

    def detect(self, frame: Frame) -> PoseResult | None:
        return self._pose


def _frames(n: int) -> list[Frame]:
    frame: Frame = np.zeros((8, 8, 3), dtype=np.uint8)
    return [frame for _ in range(n)]


def test_screenshot_artifact_saved_on_events() -> None:
    """При событиях сохраняется один скриншот и пишется строка artifacts."""
    engine = _engine()
    task_id = _insert_task(engine)
    saved: list[tuple[Frame, str]] = []
    source: FrameSource = FakeFrameSource(_frames(3))
    run_once(
        engine,
        _settings(),
        detector=_FakeDetector(_pose_arm_up()),
        sink=CollectingEventSink(),
        source_factory=lambda *_: source,
        now_fn=lambda: datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
        save_frame=lambda frame, path: saved.append((frame, path)),
    )

    assert len(saved) == 1, "Должен сохраниться ровно один скриншот на задание"
    with engine.connect() as conn:
        rows = list(conn.execute(select(artifacts)).mappings())
    assert len(rows) == 1
    row = rows[0]
    assert str(row["task_id"]) == str(task_id)
    assert row["kind"] == ArtifactKind.SCREENSHOT.value
    assert row["path"] == saved[0][1]
    assert "/data/artifacts/2026-06-06/" in row["path"]
    assert row["path"].endswith(".jpg")


def test_no_artifact_without_events() -> None:
    """Без событий скриншот не сохраняется и строк artifacts нет."""
    engine = _engine()
    _insert_task(engine)
    saved: list[tuple[Frame, str]] = []
    source: FrameSource = FakeFrameSource(_frames(1))
    run_once(
        engine,
        _settings(),
        detector=_FakeDetector(_pose_silent()),
        sink=CollectingEventSink(),
        source_factory=lambda *_: source,
        save_frame=lambda frame, path: saved.append((frame, path)),
    )

    assert saved == []
    with engine.connect() as conn:
        rows = list(conn.execute(select(artifacts)).mappings())
    assert rows == []
