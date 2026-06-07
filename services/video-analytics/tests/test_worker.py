"""Проверка воркера video-analytics: обработка задания, очередь, статус."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import Landmark, PoseLandmark, PoseResult
from video_analytics.repository import claim_next_task
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


def _insert_queued_task(engine: Engine) -> UUID:
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


def _pose_right_arm_up() -> PoseResult:
    """Поза: правое запястье выше плеча (триггерит right_arm_up)."""
    lms = [Landmark(0.5, 0.5, 1.0) for _ in range(33)]
    lms[int(PoseLandmark.RIGHT_WRIST)] = Landmark(0.5, 0.2, 1.0)
    return PoseResult(lms)


class _FakeDetector:
    """Детектор-заглушка: возвращает одну и ту же позу на каждый кадр."""

    def __init__(self, pose: PoseResult | None) -> None:
        self._pose = pose

    def detect(self, frame: Frame) -> PoseResult | None:
        return self._pose


def _frames(n: int) -> list[Frame]:
    frame: Frame = np.zeros((4, 4, 3), dtype=np.uint8)
    return [frame for _ in range(n)]


def _status(engine: Engine, task_id: UUID) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                select(analysis_tasks.c.status).where(analysis_tasks.c.id == task_id)
            ).scalar_one()
        )


def test_run_once_processes_task_and_emits_event() -> None:
    """Задание обрабатывается: эмитится pose_event и статус становится done."""
    engine = _engine()
    task_id = _insert_queued_task(engine)
    sink = CollectingEventSink()
    source: FrameSource = FakeFrameSource(_frames(3))
    detector = _FakeDetector(_pose_right_arm_up())

    processed = run_once(
        engine,
        _settings(),
        detector=detector,
        sink=sink,
        source_factory=lambda *_: source,
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
        save_frame=lambda *_: None,
    )

    assert processed
    assert any(e.type is EventType.POSE_EVENT for e in sink.events)
    assert _status(engine, task_id) == TaskStatus.DONE.value


def test_run_once_empty_queue() -> None:
    """Пустая очередь → run_once возвращает False, событий нет."""
    engine = _engine()
    sink = CollectingEventSink()
    processed = run_once(
        engine,
        _settings(),
        detector=_FakeDetector(None),
        sink=sink,
        source_factory=lambda *_: FakeFrameSource([]),
    )
    assert not processed
    assert sink.events == []


def test_run_once_marks_failed_on_error() -> None:
    """Ошибка обработки переводит задание в failed."""
    engine = _engine()
    task_id = _insert_queued_task(engine)

    def boom(*_: object) -> FrameSource:
        raise RuntimeError("источник недоступен")

    processed = run_once(
        engine,
        _settings(),
        detector=_FakeDetector(None),
        sink=CollectingEventSink(),
        source_factory=boom,
    )
    assert processed
    assert _status(engine, task_id) == TaskStatus.FAILED.value


def test_claim_next_task_marks_running() -> None:
    """claim_next_task берёт queued и переводит в running; пустая очередь → None."""
    engine = _engine()
    assert claim_next_task(engine, datetime(2026, 6, 6, 10, 0, tzinfo=UTC)) is None
    task_id = _insert_queued_task(engine)
    task = claim_next_task(engine, datetime(2026, 6, 6, 10, 1, tzinfo=UTC))
    assert task is not None
    assert task.id == task_id
    assert task.status is TaskStatus.RUNNING
    assert _status(engine, task_id) == TaskStatus.RUNNING.value
