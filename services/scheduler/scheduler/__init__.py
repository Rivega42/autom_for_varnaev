"""Планировщик заданий на видеоанализ (эпик E5).

Создаёт записи в `analysis_tasks` с `trigger=schedule` по расписаниям из конфига.
Единый механизм триггера для v1/v2: в v1 источник заданий — только наш планировщик,
в v2 к нему добавится АУРА (СТЫК-АУРА).
"""

from scheduler.config import Settings
from scheduler.dedup import create_task_if_absent, slot_window
from scheduler.repository import create_task
from scheduler.schedules import ScheduleEntry, load_schedules
from scheduler.tick import run_tick

__all__ = [
    "ScheduleEntry",
    "Settings",
    "create_task",
    "create_task_if_absent",
    "load_schedules",
    "run_tick",
    "slot_window",
]
