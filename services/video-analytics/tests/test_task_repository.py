"""Проверка чтения задания на анализ."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.repository import get_task
from video_analytics.tables import analysis_tasks, metadata

from monitoring_shared import SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def test_get_task_found() -> None:
    """Существующее задание читается в модель AnalysisTask с enum-полями."""
    engine = _engine()
    task_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=task_id,
                created_at=datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
                source_type="stream",
                source_ref="rtsp://cam-01/stream",
                room_id="room-01",
                pipeline="pose_v1",
                params={"fps": 5},
                status="queued",
                trigger="schedule",
            )
        )
    task = get_task(engine, task_id)
    assert task is not None
    assert task.source_type is SourceType.STREAM
    assert task.status is TaskStatus.QUEUED
    assert task.trigger is TaskTrigger.SCHEDULE
    assert task.pipeline == "pose_v1"


def test_get_task_missing() -> None:
    """Отсутствующее задание → None."""
    assert get_task(_engine(), uuid4()) is None
