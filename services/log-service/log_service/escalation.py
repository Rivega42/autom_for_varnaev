"""Эскалация уведомлений: повтор по неподтверждённым событиям (#264, часть 2).

Критичное событие, которое оператор не подтвердил (`POST /events/{id}/ack`) за
N минут, уведомляется повторно (через те же каналы Notifier) — до max повторов,
с паузой между повторами. Выключено по умолчанию (NOTIFY_ESCALATE_AFTER_MIN=0).

Проверка идёт фоновым потоком log-service; логика (`check_once`) — чистая и
тестируется без потока.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from log_service.notifications import Notifier
from log_service.repository import find_for_escalation, mark_escalated
from monitoring_shared import Event, EventSource, EventType, Severity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EscalationSettings:
    """Параметры эскалации (0 минут = выключена)."""

    after_min: int = 0
    repeat_min: int = 30
    max_repeats: int = 3
    severities: tuple[str, ...] = ("critical",)

    @classmethod
    def from_env(cls) -> EscalationSettings:
        """Собрать из окружения; мусор в числах → безопасные значения."""

        def _int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)).strip())
            except ValueError:
                logger.warning("%s некорректен — использую %d", name, default)
                return default

        sev_env = os.getenv("NOTIFY_ESCALATE_SEVERITIES", "critical")
        severities = tuple(s.strip() for s in sev_env.split(",") if s.strip()) or ("critical",)
        return cls(
            after_min=_int("NOTIFY_ESCALATE_AFTER_MIN", 0),
            repeat_min=_int("NOTIFY_ESCALATE_REPEAT_MIN", 30),
            max_repeats=_int("NOTIFY_ESCALATE_MAX", 3),
            severities=severities,
        )


def _row_to_event(row: Any) -> Event:
    """Собрать Event из строки events (для повторного форматирования)."""
    return Event(
        id=row["id"] if isinstance(row["id"], UUID) else UUID(str(row["id"])),
        ts=row["ts"] if row["ts"].tzinfo else row["ts"].replace(tzinfo=UTC),
        source=EventSource(row["source"]),
        type=EventType(row["type"]),
        room_id=row["room_id"],
        severity=Severity(row["severity"]),
        message=row["message"],
        payload=row["payload"] or {},
        artifact_id=row["artifact_id"],
    )


class Escalator:
    """Повторные уведомления по неподтверждённым событиям."""

    def __init__(self, notifier: Notifier, settings: EscalationSettings) -> None:
        self._notifier = notifier
        self._settings = settings

    def check_once(self, engine: Engine, now: datetime) -> int:
        """Один проход: найти «зависшие» события и уведомить повторно."""
        s = self._settings
        if s.after_min <= 0:
            return 0
        rows = find_for_escalation(
            engine,
            severities=s.severities,
            older_than=now - timedelta(minutes=s.after_min),
            repeat_after=now - timedelta(minutes=s.repeat_min),
            max_count=s.max_repeats,
        )
        sent = 0
        for row in rows:
            event = _row_to_event(row)
            repeat_no = int(row["escalation_count"]) + 1
            # Помечаем повтор в тексте — оператор видит, что событие «висит».
            escalated = event.model_copy(
                update={"message": f"ПОВТОР {repeat_no} (не подтверждено): {event.message}"}
            )
            self._notifier.notify(escalated)
            mark_escalated(engine, event.id, now)
            sent += 1
        if sent:
            logger.info("Эскалация: повторно уведомлено событий: %d", sent)
        return sent

    def run_forever(self, engine: Engine, *, interval_s: float = 60.0) -> None:
        """Фоновый цикл (daemon-поток): проверка раз в interval_s."""
        while True:
            try:
                self.check_once(engine, datetime.now(UTC))
            except Exception:
                logger.exception("Эскалация: ошибка прохода, продолжаем")
            time.sleep(interval_s)


def start_escalator_thread(engine: Engine, notifier: Notifier) -> Escalator | None:
    """Запустить фоновый эскалятор, если он включён в окружении; иначе None."""
    settings = EscalationSettings.from_env()
    if settings.after_min <= 0:
        return None
    escalator = Escalator(notifier, settings)
    thread = threading.Thread(
        target=escalator.run_forever, args=(engine,), daemon=True, name="escalator"
    )
    thread.start()
    logger.info(
        "Эскалация включена: повтор через %d мин (пауза %d мин, максимум %d, важность: %s)",
        settings.after_min,
        settings.repeat_min,
        settings.max_repeats,
        ",".join(settings.severities),
    )
    return escalator
