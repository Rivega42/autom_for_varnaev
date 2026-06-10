"""Монитор контроля уборки: связывает правила, журнал и сток событий (#265).

Вызывается из цикла планировщика на каждом тике: загружает включённые правила и
последние уборки (coverage_report), оценивает просрочки чистым ядром
(`cleaning.evaluate_overdue`) и эмитит cleaning_overdue в log-service. Состояние
эпизодов (по каким зонам уже сообщили) живёт в мониторе между тиками.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Engine

from scheduler.cleaning import evaluate_overdue
from scheduler.cleaning_store import load_cleaning_rules, load_last_cleanings
from scheduler.events import EventSink, build_cleaning_overdue

logger = logging.getLogger(__name__)


class CleaningMonitor:
    """Проверка «убрано ли вовремя» с памятью эпизодов между тиками."""

    def __init__(self, sink: EventSink) -> None:
        self._sink = sink
        self._flagged: set[tuple[str, str]] = set()

    def check(self, engine: Engine, now: datetime) -> int:
        """Один проход: оценить правила и отправить новые просрочки; вернуть число."""
        rules = load_cleaning_rules(engine)
        if not rules:
            return 0
        last = load_last_cleanings(engine, rules, now)
        results, self._flagged = evaluate_overdue(rules, last, now, self._flagged)
        for result in results:
            self._sink.emit(build_cleaning_overdue(result, now))
            logger.info("Контроль уборки: %s", result.message)
        return len(results)
