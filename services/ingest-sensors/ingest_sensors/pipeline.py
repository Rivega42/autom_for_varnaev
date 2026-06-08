"""Связка обработки входящего MQTT-сообщения: разбор → запись → события.

Собирает MessageHandler для воркера: разбирает показание, пишет его в БД и (если
переданы монитор порогов и сток событий) формирует события превышения/возврата к
норме и отправляет их в единый журнал.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ingest_sensors.events import (
    EventSink,
    RoomDescriber,
    build_back_to_normal,
    build_threshold_exceeded,
    default_room_describer,
)
from ingest_sensors.mqtt import MessageHandler
from ingest_sensors.parsing import RoomResolver, parse_message
from ingest_sensors.thresholds import ThresholdMonitor, Transition
from monitoring_shared import Reading

logger = logging.getLogger(__name__)


class ReadingWriter(Protocol):
    """Писатель показаний (DbReadingWriter и фейки в тестах)."""

    def write(self, reading: Reading) -> None: ...


def make_reading_handler(
    writer: ReadingWriter,
    resolve_room: RoomResolver,
    *,
    monitor: ThresholdMonitor | None = None,
    sink: EventSink | None = None,
    describe_room: RoomDescriber = default_room_describer,
) -> MessageHandler:
    """Создать обработчик: разобрать сообщение в Reading, записать и эмитить события.

    Битые/неизвестные сообщения parse_message отсекает (None) — запись не делается.
    Если `monitor` и `sink` заданы, по переходам порога эмитятся события
    THRESHOLD_EXCEEDED / BACK_TO_NORMAL. Обработчик отказоустойчив: исключение на
    одном сообщении логируется и не роняет цикл приёма.
    """

    def handle(topic: str, payload: bytes) -> None:
        try:
            reading = parse_message(topic, payload, resolve_room)
            if reading is None:
                return
            writer.write(reading)

            if monitor is None or sink is None:
                return
            transition, threshold = monitor.evaluate(reading.room_id, reading.metric, reading.value)
            if transition is Transition.BREACHED and threshold is not None:
                sink.emit(build_threshold_exceeded(reading, threshold, describe_room))
            elif transition is Transition.RECOVERED:
                sink.emit(build_back_to_normal(reading, describe_room))
        except Exception:
            # Одно битое сообщение/сбой БД не должны ронять приём по MQTT.
            logger.exception("Ошибка обработки сообщения из топика %s", topic)

    return handle
