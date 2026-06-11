"""Монитор присутствия в рабочей зоне по окну времени (#300).

Вызывается из цикла планировщика на каждом тике: загружает включённые правила
(presence_rules) и последние присутствия (события presence_detected, #302),
оценивает отсутствия чистым ядром (`presence_control.evaluate_missing`) и эмитит
presence_missing в log-service. Окна правил заданы в часовом поясе PRESENCE_TZ —
время тика переводится в него перед сравнением. Состояние эпизодов живёт в
мониторе между тиками.
"""

from __future__ import annotations

import logging
from datetime import datetime, tzinfo

from sqlalchemy import Engine

from scheduler.events import EventSink, build_presence_missing
from scheduler.presence_control import evaluate_missing
from scheduler.presence_store import load_last_presence, load_presence_rules

logger = logging.getLogger(__name__)


class PresenceMonitor:
    """Проверка «есть ли персонал в окне» с памятью эпизодов между тиками."""

    def __init__(self, sink: EventSink, tz: tzinfo) -> None:
        self._sink = sink
        self._tz = tz
        self._flagged: set[int] = set()

    def check(self, engine: Engine, now: datetime) -> int:
        """Один проход: оценить правила и отправить новые отсутствия; вернуть число."""
        rules = load_presence_rules(engine)
        if not rules:
            return 0
        last = load_last_presence(engine, now)
        local_now = now.astimezone(self._tz)  # окна правил — в PRESENCE_TZ
        results, self._flagged = evaluate_missing(rules, last, local_now, self._flagged)
        for result in results:
            self._sink.emit(build_presence_missing(result, now))
            logger.warning("Контроль присутствия: %s", result.message)
        return len(results)
