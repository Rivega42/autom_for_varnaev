"""Точка входа демона-планировщика: периодический тик по расписаниям.

Процесс читает расписания из файла (`Settings.schedules_path`) и каждые
`tick_interval_s` секунд создаёт недостающие задания на анализ (`run_tick`).
Запуск: `python -m scheduler.main`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Engine

from monitoring_shared import install_stop_event
from scheduler.camera_liveness import CameraLivenessMonitor
from scheduler.camera_store import Go2rtcCameraProber
from scheduler.cleaning_monitor import CleaningMonitor
from scheduler.config import Settings
from scheduler.db import build_engine
from scheduler.events import HttpEventSink
from scheduler.heartbeat import write_heartbeat
from scheduler.presence_monitor import PresenceMonitor
from scheduler.schedules import ScheduleEntry, load_schedules, load_schedules_db
from scheduler.tick import run_tick
from scheduler.watchdog import ServiceWatchdog

logger = logging.getLogger(__name__)


def _merged_schedules(engine: Engine, settings: Settings) -> list[ScheduleEntry]:
    """Расписания из БД (источник истины GUI) + из файла (легаси), БД приоритетна.

    Записи файла добавляются, только если имя не занято записью из БД.
    """
    db_entries = load_schedules_db(engine)
    names = {e.name for e in db_entries}
    file_entries = [e for e in load_schedules(settings.schedules_path) if e.name not in names]
    return db_entries + file_entries


def tick_once(engine: Engine, settings: Settings, now: datetime) -> int:
    """Один проход: прочитать расписания (БД+файл) и создать недостающие задания.

    Возвращает число созданных заданий (для логов и тестов).
    """
    entries = _merged_schedules(engine, settings)
    created = run_tick(engine, entries, now)
    return len(created)


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


def run_forever(
    engine: Engine,
    settings: Settings,
    *,
    # object, а не None: сюда удобно передавать Event.wait (возвращает bool).
    sleep: Callable[[float], object] = time.sleep,
    now_fn: Callable[[], datetime] = _now_utc,
    max_iterations: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    cleaning_monitor: CleaningMonitor | None = None,
    camera_monitor: CameraLivenessMonitor | None = None,
    watchdog: ServiceWatchdog | None = None,
    presence_monitor: PresenceMonitor | None = None,
    service_name: str = "scheduler",
) -> None:
    """Цикл планировщика: тик, затем сон на `tick_interval_s`, и так по кругу.

    Демон не должен падать из-за ошибки одного тика — исключение логируется,
    цикл продолжается. `max_iterations` ограничивает число итераций (для тестов);
    при `None` цикл бесконечный. `cleaning_monitor` (если задан) проверяет на
    каждом тике контроль уборки (#265); `camera_monitor` — живость камер (#283);
    `watchdog` — свежесть heartbeat'ов сервисов (#284); `presence_monitor` —
    присутствие в рабочих зонах по окну времени (#300). Планировщик пишет и свой
    heartbeat на каждой итерации. `should_stop` — мягкая остановка (#206):
    проверяется перед каждой итерацией.
    """
    iteration = 0
    while True:
        if should_stop is not None and should_stop():
            logger.info("Планировщик: получен сигнал остановки — выходим из цикла")
            return
        now = now_fn()  # один момент времени на итерацию (тик + мониторы)
        write_heartbeat(engine, service_name, now)  # отметка живости самого планировщика
        try:
            count = tick_once(engine, settings, now)
            if count:
                logger.info("Планировщик: тик создал заданий: %d", count)
        except Exception:
            logger.exception("Планировщик: ошибка в тике, продолжаем")
        if cleaning_monitor is not None:
            try:
                cleaning_monitor.check(engine, now)
            except Exception:
                # Сбой контроля уборки не должен мешать созданию заданий.
                logger.exception("Контроль уборки: ошибка проверки, продолжаем")
        if camera_monitor is not None:
            try:
                camera_monitor.check(engine, now)
            except Exception:
                # Сбой пробы камер не должен мешать остальным проверкам.
                logger.exception("Живость камер: ошибка проверки, продолжаем")
        if watchdog is not None:
            try:
                watchdog.check(engine, now)
            except Exception:
                # Сбой watchdog не должен мешать остальным проверкам.
                logger.exception("Watchdog сервисов: ошибка проверки, продолжаем")
        if presence_monitor is not None:
            try:
                presence_monitor.check(engine, now)
            except Exception:
                # Сбой контроля присутствия не должен мешать остальным проверкам.
                logger.exception("Контроль присутствия: ошибка проверки, продолжаем")
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            return
        sleep(settings.tick_interval_s)


def main() -> None:
    """Настроить логирование, собрать настройки/engine и запустить цикл."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    settings = Settings.from_env()
    engine = build_engine()
    logger.info(
        "Планировщик запущен: расписания=%s, период тика=%d c",
        settings.schedules_path,
        settings.tick_interval_s,
    )
    sink = HttpEventSink(settings.log_service_url)
    cleaning = CleaningMonitor(sink)
    cameras = CameraLivenessMonitor(
        sink,
        Go2rtcCameraProber(settings.go2rtc_url, timeout=settings.camera_probe_timeout_s),
    )
    watchdog = ServiceWatchdog(sink, settings.service_silent_min)
    presence = PresenceMonitor(sink, ZoneInfo(settings.presence_tz))
    # Мягкая остановка по SIGTERM/SIGINT (#206): docker stop завершает цикл
    # между тиками, сон прерывается сразу (sleep = stop.wait).
    stop = install_stop_event()
    try:
        run_forever(
            engine,
            settings,
            cleaning_monitor=cleaning,
            camera_monitor=cameras,
            watchdog=watchdog,
            presence_monitor=presence,
            sleep=stop.wait,
            should_stop=stop.is_set,
        )
    finally:
        engine.dispose()
        logger.info("Планировщик остановлен штатно")


if __name__ == "__main__":
    main()
