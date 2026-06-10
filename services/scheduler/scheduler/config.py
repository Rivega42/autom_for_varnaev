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
    # Журнал событий: сюда уходят cleaning_overdue (контроль уборки, #265).
    log_service_url: str = "http://log-service:8000"
    # Медиа-шлюз go2rtc: проба живости камер (#283).
    go2rtc_url: str = "http://media-gateway:1984"
    # Порог «тишины» сервиса (watchdog, #284): нет heartbeat дольше N минут.
    service_silent_min: int = 5

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения (значения по умолчанию — как в compose)."""
        return cls(
            schedules_path=os.getenv("SCHEDULER_CONFIG", "/config/schedules.json"),
            tick_interval_s=int(os.getenv("SCHEDULER_TICK_S", "60")),
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            go2rtc_url=os.getenv("GO2RTC_URL", "http://media-gateway:1984"),
            service_silent_min=int(os.getenv("SERVICE_SILENT_MIN", "5")),
        )
