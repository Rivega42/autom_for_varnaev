"""Конфигурация планировщика из переменных окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Параметры планировщика."""

    # Путь к JSON-файлу с расписаниями (список ScheduleEntry).
    schedules_path: str
    # Периодичность тика планировщика, секунд (как часто сверять расписания).
    tick_interval_s: int

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения (значения по умолчанию — как в compose)."""
        return cls(
            schedules_path=os.getenv("SCHEDULER_CONFIG", "/config/schedules.json"),
            tick_interval_s=int(os.getenv("SCHEDULER_TICK_S", "60")),
        )
