"""Проверка предотвращения дублей заданий по слотам расписания."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scheduler.dedup import create_task_if_absent, slot_window
from scheduler.schedules import ScheduleEntry
from scheduler.tables import analysis_tasks, metadata
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool

from monitoring_shared import SourceType


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
    )


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return len(conn.execute(select(analysis_tasks)).all())


def test_slot_window_aligns_to_interval() -> None:
    """Окно слота выровнено по периоду и содержит момент now."""
    start, end = slot_window(datetime(2026, 6, 5, 10, 17, tzinfo=UTC), 30)
    assert start == datetime(2026, 6, 5, 10, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 5, 10, 30, tzinfo=UTC)


def test_no_duplicate_in_same_slot() -> None:
    """Повторный вызов в том же слоте не создаёт второе задание."""
    engine = _engine()
    entry = _entry()
    first = create_task_if_absent(engine, entry, datetime(2026, 6, 5, 10, 5, tzinfo=UTC))
    second = create_task_if_absent(engine, entry, datetime(2026, 6, 5, 10, 25, tzinfo=UTC))
    assert first is not None
    assert second is None
    assert _count(engine) == 1


def test_new_slot_creates_task() -> None:
    """В следующем слоте создаётся новое задание."""
    engine = _engine()
    entry = _entry()
    create_task_if_absent(engine, entry, datetime(2026, 6, 5, 10, 5, tzinfo=UTC))
    nxt = create_task_if_absent(
        engine, entry, datetime(2026, 6, 5, 10, 5, tzinfo=UTC) + timedelta(minutes=30)
    )
    assert nxt is not None
    assert _count(engine) == 2


def test_dedup_is_per_entry() -> None:
    """Разные записи (разный источник) не мешают друг другу в одном слоте."""
    engine = _engine()
    now = datetime(2026, 6, 5, 10, 5, tzinfo=UTC)
    a = _entry()
    b = ScheduleEntry(
        name="room-02-pose",
        source_type=SourceType.STREAM,
        source_ref="rtsp://cam-02/stream",
        pipeline="pose_v1",
        interval_min=30,
    )
    assert create_task_if_absent(engine, a, now) is not None
    assert create_task_if_absent(engine, b, now) is not None
    assert _count(engine) == 2
