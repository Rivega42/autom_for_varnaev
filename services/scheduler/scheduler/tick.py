"""Один проход планировщика: создание недостающих заданий по расписаниям.

`run_tick` обходит список расписаний и для каждого создаёт задание на текущий
слот, если его ещё нет (дедуп — в `dedup.create_task_if_absent`). Вызывается
периодически (период тика — `Settings.tick_interval_s`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine

from scheduler.dedup import create_task_if_absent
from scheduler.schedules import ScheduleEntry

logger = logging.getLogger(__name__)


def run_tick(engine: Engine, entries: Iterable[ScheduleEntry], now: datetime) -> list[UUID]:
    """Создать задания для записей, у которых нет задания в текущем слоте.

    Возвращает список id созданных заданий (для уже существующих слотов — пусто).
    """
    created: list[UUID] = []
    for entry in entries:
        task_id = create_task_if_absent(engine, entry, now)
        if task_id is not None:
            created.append(task_id)
            logger.info(
                "Планировщик: создано задание %s по расписанию «%s» (%s)",
                task_id,
                entry.name,
                entry.pipeline,
            )
    return created
