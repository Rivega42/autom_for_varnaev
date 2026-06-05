"""Формирование событий датчиков и их отправка в «сток» (единый журнал).

Сток — абстракция (Protocol): в v1 по умолчанию логирование, доставка в
log-service по REST подключается при готовности log-service (эпик E3).
Сообщения событий — человекочитаемые, на русском, с контекстом помещения
(дополнение ТЗ, см. docs/04_DATA_MODEL.md §4).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from monitoring_shared import (
    Event,
    EventSource,
    EventType,
    Metric,
    Reading,
    Threshold,
    ThresholdOp,
)

logger = logging.getLogger(__name__)

# Описатель помещения: room_id -> предложный оборот («холодильной камере»).
RoomDescriber = Callable[[str | None], str]

# Человекочитаемые названия метрик.
_METRIC_HUMAN: dict[Metric, str] = {
    Metric.AIR_TEMP: "температура",
    Metric.HUMIDITY: "влажность",
    Metric.SURFACE_IR: "температура поверхности",
}


def default_room_describer(room_id: str | None) -> str:
    """Описание помещения по умолчанию (если нет справочника имён)."""
    return f"помещении {room_id}" if room_id else "помещении"


def _metric_human(metric: Metric) -> str:
    return _METRIC_HUMAN.get(metric, metric.value)


def _direction(op: ThresholdOp) -> str:
    """Сторона нарушения порога: «выше» для >/>=, «ниже» для </<=."""
    return "выше" if op in (ThresholdOp.GT, ThresholdOp.GE) else "ниже"


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


class EventSink(Protocol):
    """Сток событий: получатель сформированных событий."""

    def emit(self, event: Event) -> None: ...


class LoggingEventSink:
    """Сток по умолчанию (v1): пишет событие в лог оператора."""

    def emit(self, event: Event) -> None:
        logger.info("Событие [%s] %s", event.type.value, event.message)


def build_threshold_exceeded(
    reading: Reading,
    threshold: Threshold,
    describe_room: RoomDescriber = default_room_describer,
) -> Event:
    """Сформировать событие превышения порога с человекочитаемым message."""
    message = _capitalize(
        f"в {describe_room(reading.room_id)} "
        f"{_metric_human(reading.metric)} {_direction(threshold.op)} нормы"
    )
    return Event(
        id=uuid4(),
        ts=reading.ts,
        source=EventSource.SENSORS,
        type=EventType.THRESHOLD_EXCEEDED,
        room_id=reading.room_id,
        severity=threshold.severity,
        message=message,
        payload={
            "metric": reading.metric.value,
            "value": reading.value,
            "threshold": threshold.value,
            "op": threshold.op.value,
        },
    )
