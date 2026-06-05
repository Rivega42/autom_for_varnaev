"""Проверка создания задания на анализ по расписанию."""

from __future__ import annotations

from datetime import UTC, datetime

from scheduler.repository import create_task
from scheduler.schedules import ScheduleEntry
from scheduler.tables import analysis_tasks, metadata
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool

from monitoring_shared import SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _entry() -> ScheduleEntry:
    return ScheduleEntry(
        name="room-01-pose",
        source_type=SourceType.STREAM,
        source_ref="rtsp://cam-01/stream",
        pipeline="pose_v1",
        room_id="room-01",
        interval_min=30,
        params={"fps": 5},
    )


def test_create_task_fields() -> None:
    """Задание создаётся со status=queued, trigger=schedule и полями из расписания."""
    engine = _engine()
    now = datetime(2026, 6, 5, 10, 0, tzinfo=UTC)
    task_id = create_task(engine, _entry(), now)

    with engine.connect() as conn:
        row = (
            conn.execute(select(analysis_tasks).where(analysis_tasks.c.id == task_id))
            .mappings()
            .one()
        )

    assert row["status"] == TaskStatus.QUEUED.value
    assert row["trigger"] == TaskTrigger.SCHEDULE.value
    assert row["source_type"] == SourceType.STREAM.value
    assert row["source_ref"] == "rtsp://cam-01/stream"
    assert row["room_id"] == "room-01"
    assert row["pipeline"] == "pose_v1"
    assert row["params"] == {"fps": 5}
    # SQLite хранит datetime без tzinfo — нормализуем перед сравнением.
    created = row["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    assert created == now


def test_create_task_returns_unique_ids() -> None:
    """Каждый вызов создаёт отдельное задание с уникальным id."""
    engine = _engine()
    now = datetime(2026, 6, 5, 10, 0, tzinfo=UTC)
    a = create_task(engine, _entry(), now)
    b = create_task(engine, _entry(), now)
    assert a != b
    with engine.connect() as conn:
        count = conn.execute(select(analysis_tasks)).all()
    assert len(count) == 2
