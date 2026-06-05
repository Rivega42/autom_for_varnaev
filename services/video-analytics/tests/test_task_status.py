"""Проверка обновления статуса задания на анализ."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.repository import get_task, mark_done, mark_failed, mark_running
from video_analytics.tables import analysis_tasks, metadata

from monitoring_shared import TaskStatus

_T0 = datetime(2026, 6, 5, 10, 0, tzinfo=UTC)


def _engine_with_task(task_id: object) -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=task_id,
                created_at=_T0,
                source_type="stream",
                source_ref="rtsp://cam-01/stream",
                room_id="room-01",
                pipeline="pose_v1",
                status="queued",
                trigger="schedule",
            )
        )
    return engine


def test_mark_running_then_done() -> None:
    task_id = uuid4()
    engine = _engine_with_task(task_id)
    mark_running(engine, task_id, _T0)
    task = get_task(engine, task_id)
    assert task is not None and task.status is TaskStatus.RUNNING
    assert task.started_at is not None

    mark_done(engine, task_id, _T0 + timedelta(seconds=10), result={"events": 3})
    task = get_task(engine, task_id)
    assert task is not None and task.status is TaskStatus.DONE
    assert task.finished_at is not None
    assert task.result == {"events": 3}


def test_mark_failed() -> None:
    task_id = uuid4()
    engine = _engine_with_task(task_id)
    mark_failed(engine, task_id, _T0, "источник недоступен")
    task = get_task(engine, task_id)
    assert task is not None and task.status is TaskStatus.FAILED
    assert task.error == "источник недоступен"
