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

from sqlalchemy import Engine

from scheduler.config import Settings
from scheduler.db import build_engine
from scheduler.schedules import ScheduleEntry, load_schedules, load_schedules_db
from scheduler.tick import run_tick

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
    sleep: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] = _now_utc,
    max_iterations: int | None = None,
) -> None:
    """Цикл планировщика: тик, затем сон на `tick_interval_s`, и так по кругу.

    Демон не должен падать из-за ошибки одного тика — исключение логируется,
    цикл продолжается. `max_iterations` ограничивает число итераций (для тестов);
    при `None` цикл бесконечный.
    """
    iteration = 0
    while True:
        try:
            count = tick_once(engine, settings, now_fn())
            if count:
                logger.info("Планировщик: тик создал заданий: %d", count)
        except Exception:
            logger.exception("Планировщик: ошибка в тике, продолжаем")
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
    run_forever(engine, settings)


if __name__ == "__main__":
    main()
