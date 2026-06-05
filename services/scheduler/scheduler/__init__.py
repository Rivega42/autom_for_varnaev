"""Планировщик заданий на видеоанализ (эпик E5).

Создаёт записи в `analysis_tasks` с `trigger=schedule` по расписаниям из конфига.
Единый механизм триггера для v1/v2: в v1 источник заданий — только наш планировщик,
в v2 к нему добавится АУРА (СТЫК-АУРА).
"""

from scheduler.config import Settings
from scheduler.schedules import ScheduleEntry, load_schedules

__all__ = ["ScheduleEntry", "Settings", "load_schedules"]
