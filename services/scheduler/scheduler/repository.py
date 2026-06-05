"""Создание заданий на анализ (analysis_tasks) по расписанию."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine

from monitoring_shared import TaskStatus, TaskTrigger
from scheduler.schedules import ScheduleEntry
from scheduler.tables import analysis_tasks


def create_task(engine: Engine, entry: ScheduleEntry, now: datetime) -> UUID:
    """Создать задание `queued`/`schedule` из записи расписания, вернуть его id.

    Поля источника и пайплайна переносятся из `ScheduleEntry`; жизненный цикл
    начинается с `queued` (см. docs/04_DATA_MODEL.md §5). Триггер — всегда
    `schedule`: это наш планировщик (в v2 добавится `aura`).
    """
    task_id = uuid4()
    stmt = analysis_tasks.insert().values(
        id=task_id,
        created_at=now,
        source_type=entry.source_type.value,
        source_ref=entry.source_ref,
        room_id=entry.room_id,
        pipeline=entry.pipeline,
        params=entry.params,
        status=TaskStatus.QUEUED.value,
        trigger=TaskTrigger.SCHEDULE.value,
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return task_id
