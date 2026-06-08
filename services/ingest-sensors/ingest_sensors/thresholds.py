"""Сверка показаний с порогами и отслеживание состояния «выше/в норме».

Загружает пороги из таблицы thresholds, применяет к показаниям (Reading) и
по переходам состояния (room, metric) сообщает о срабатывании/возврате к норме.
События формируются на основе этих переходов в E2.8–E2.9.
"""

from __future__ import annotations

import operator
import threading
from collections.abc import Callable
from enum import StrEnum, auto

from sqlalchemy import Engine, text

from monitoring_shared import Metric, Threshold, ThresholdOp

# Операторы сравнения порога.
_OPS: dict[ThresholdOp, Callable[[float, float], bool]] = {
    ThresholdOp.GT: operator.gt,
    ThresholdOp.LT: operator.lt,
    ThresholdOp.GE: operator.ge,
    ThresholdOp.LE: operator.le,
}


def compare(op: ThresholdOp, value: float, threshold_value: float) -> bool:
    """Истина, если value нарушает порог по оператору op."""
    return _OPS[op](value, threshold_value)


class Transition(StrEnum):
    """Переход состояния (room, metric) по порогу."""

    NONE = auto()  # состояние не изменилось
    BREACHED = auto()  # норма → превышение
    RECOVERED = auto()  # превышение → норма


def applicable_thresholds(
    thresholds: list[Threshold], room_id: str | None, metric: Metric
) -> list[Threshold]:
    """Пороги, применимые к (room, metric): включённые, по метрике, глобальные или
    этого помещения."""
    return [
        t
        for t in thresholds
        if t.enabled and t.metric == metric and (t.room_id is None or t.room_id == room_id)
    ]


def resolve_silent_min(thresholds: list[Threshold], room_id: str | None, default: int) -> int:
    """Порог «тишины» для помещения по контракту (docs/08, docs/04 §4).

    Берёт минимальный (самый строгий) `silent_min` среди применимых к помещению
    включённых порогов (глобальных или этого помещения). Если ни один порог
    не задаёт `silent_min` — возвращает `default` (общий запасной порог из env).
    «Тишина» не привязана к конкретной метрике, поэтому метрику здесь не фильтруем.
    """
    candidates = [
        t.silent_min
        for t in thresholds
        if t.enabled and t.silent_min is not None and (t.room_id is None or t.room_id == room_id)
    ]
    return min(candidates) if candidates else default


def load_thresholds(engine: Engine) -> list[Threshold]:
    """Загрузить включённые пороги из БД."""
    query = text(
        "SELECT id, room_id, metric, op, value, severity, silent_min, enabled "
        "FROM thresholds WHERE enabled"
    )
    with engine.connect() as conn:
        return [Threshold(**dict(row)) for row in conn.execute(query).mappings()]


class ThresholdMonitor:
    """Хранит пороги и состояние превышения по (room, metric).

    Потокобезопасен: `evaluate` вызывается из сетевого потока MQTT (обработка
    показаний), а `replace`/`silent_min_for` — из основного потока (тик с горячей
    перезагрузкой порогов). Доступ к разделяемому состоянию под общим Lock.
    """

    def __init__(self, thresholds: list[Threshold]) -> None:
        self._thresholds = thresholds
        # ключ (room_id, metric) -> сработавший порог
        self._breached: dict[tuple[str | None, Metric], Threshold] = {}
        self._lock = threading.Lock()

    def replace(self, thresholds: list[Threshold]) -> None:
        """Заменить набор порогов (горячая перезагрузка из БД при правках в GUI).

        Заодно отбрасывает «зависшее» состояние превышения для (room, metric),
        для которых в новом наборе больше нет ни одного применимого порога:
        иначе следующее показание в норме породило бы ложный BACK_TO_NORMAL по
        уже удалённому/выключенному порогу.
        """
        with self._lock:
            self._thresholds = thresholds
            self._breached = {
                key: t
                for key, t in self._breached.items()
                if applicable_thresholds(thresholds, key[0], key[1])
            }

    def silent_min_for(self, room_id: str | None, default: int) -> int:
        """Порог «тишины» для помещения по текущему набору порогов (см. resolve_silent_min)."""
        with self._lock:
            return resolve_silent_min(self._thresholds, room_id, default)

    def evaluate(
        self, room_id: str | None, metric: Metric, value: float
    ) -> tuple[Transition, Threshold | None]:
        """Сверить значение с порогами и вернуть переход состояния и связанный порог."""
        with self._lock:
            breached = next(
                (
                    t
                    for t in applicable_thresholds(self._thresholds, room_id, metric)
                    if compare(t.op, value, t.value)
                ),
                None,
            )
            key = (room_id, metric)
            was_breached = key in self._breached

            if breached is not None and not was_breached:
                self._breached[key] = breached
                return Transition.BREACHED, breached
            if breached is None and was_breached:
                previous = self._breached.pop(key)
                return Transition.RECOVERED, previous
            return Transition.NONE, breached
