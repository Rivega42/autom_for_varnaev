"""Watchdog живости сервисов: heartbeat'ы → service_silent/service_restored (#284).

Планировщик на каждом тике читает `service_heartbeats`, и если сервис не обновлял
свою строку дольше `silent_min`, эмитит `service_silent` (один раз на эпизод);
при возвращении сервиса — `service_restored`. Симметрично «тишине» узла датчика.
Отслеживаются только сервисы, хоть раз приславшие heartbeat (как и с узлами).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from scheduler.events import EventSink, build_service_restored, build_service_silent
from scheduler.heartbeat import load_heartbeats

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Привести naive-время (SQLite в тестах) к UTC; aware — без изменений."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass(frozen=True)
class SilentService:
    """Замолчавший сервис и на сколько минут он отстал."""

    service: str
    silent_for_min: int


def evaluate_silent(
    heartbeats: dict[str, datetime],
    now: datetime,
    silent_min: int,
    flagged: set[str],
) -> tuple[list[SilentService], list[str], set[str]]:
    """Чистая оценка: вернуть (новые замолчавшие, восстановившиеся, новый flagged).

    Сервис «молчит», если с последнего heartbeat прошло больше `silent_min` минут.
    Событие — раз на эпизод: повторно не сообщаем, пока сервис не вернётся.
    """
    threshold = timedelta(minutes=silent_min)
    new_flagged = set(flagged)
    newly_silent: list[SilentService] = []
    recovered: list[str] = []
    for service, ts in heartbeats.items():
        elapsed = _as_utc(now) - _as_utc(ts)
        if elapsed > threshold:
            if service not in new_flagged:
                new_flagged.add(service)
                newly_silent.append(SilentService(service, int(elapsed.total_seconds() // 60)))
        elif service in new_flagged:
            new_flagged.discard(service)
            recovered.append(service)
    return newly_silent, recovered, new_flagged


class ServiceWatchdog:
    """Проверка свежести heartbeat'ов с памятью эпизодов между тиками."""

    def __init__(self, sink: EventSink, silent_min: int) -> None:
        self._sink = sink
        self._silent_min = silent_min
        self._flagged: set[str] = set()

    def check(self, engine: Engine, now: datetime) -> int:
        """Один проход: оценить свежесть и отправить новые события; вернуть число."""
        heartbeats = load_heartbeats(engine)
        newly_silent, recovered, self._flagged = evaluate_silent(
            heartbeats, now, self._silent_min, self._flagged
        )
        for item in newly_silent:
            self._sink.emit(build_service_silent(item.service, item.silent_for_min, now))
            logger.warning("Сервис %s молчит %d мин", item.service, item.silent_for_min)
        for service in recovered:
            self._sink.emit(build_service_restored(service, now))
            logger.info("Сервис %s снова на связи", service)
        return len(newly_silent) + len(recovered)
