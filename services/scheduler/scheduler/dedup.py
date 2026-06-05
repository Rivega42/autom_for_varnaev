"""Предотвращение дублей: одно задание на один временной слот расписания.

Время бьётся на слоты длиной `interval_min` начиная с эпохи Unix: слот — это
полуинтервал `[slot_start, slot_start + interval)`. Повторный тик планировщика в
пределах одного слота не должен создавать второе задание для той же записи
расписания.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, select

from monitoring_shared import TaskTrigger
from scheduler.repository import create_task
from scheduler.schedules import ScheduleEntry
from scheduler.tables import analysis_tasks


def slot_window(now: datetime, interval_min: int) -> tuple[datetime, datetime]:
    """Вернуть границы слота `[начало, конец)`, в который попадает `now`."""
    epoch_min = int(now.timestamp() // 60)
    slot_start_min = (epoch_min // interval_min) * interval_min
    start = datetime.fromtimestamp(slot_start_min * 60, tz=UTC)
    return start, start + timedelta(minutes=interval_min)


def task_exists_for_slot(engine: Engine, entry: ScheduleEntry, now: datetime) -> bool:
    """Проверить, есть ли уже задание этой записи в текущем слоте."""
    start, end = slot_window(now, entry.interval_min)
    stmt = (
        select(analysis_tasks.c.id)
        .where(
            analysis_tasks.c.trigger == TaskTrigger.SCHEDULE.value,
            analysis_tasks.c.source_ref == entry.source_ref,
            analysis_tasks.c.pipeline == entry.pipeline,
            analysis_tasks.c.created_at >= start,
            analysis_tasks.c.created_at < end,
        )
        .limit(1)
    )
    with engine.connect() as conn:
        return conn.execute(stmt).first() is not None


def create_task_if_absent(engine: Engine, entry: ScheduleEntry, now: datetime) -> UUID | None:
    """Создать задание, только если в текущем слоте его ещё нет.

    Возвращает id созданного задания или None, если задание на этот слот уже было.
    """
    if task_exists_for_slot(engine, entry, now):
        return None
    return create_task(engine, entry, now)
