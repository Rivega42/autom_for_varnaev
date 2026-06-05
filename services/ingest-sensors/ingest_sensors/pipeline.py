"""Связка обработки входящего MQTT-сообщения: разбор → запись в БД.

Собирает MessageHandler для воркера из парсера показаний и писателя в БД.
"""

from __future__ import annotations

import logging

from ingest_sensors.db import DbReadingWriter
from ingest_sensors.mqtt import MessageHandler
from ingest_sensors.parsing import RoomResolver, parse_message

logger = logging.getLogger(__name__)


def make_reading_handler(writer: DbReadingWriter, resolve_room: RoomResolver) -> MessageHandler:
    """Создать обработчик: разобрать сообщение в Reading и записать в БД.

    Битые/неизвестные сообщения parse_message отсекает (None) — запись не делается.
    """

    def handle(topic: str, payload: bytes) -> None:
        reading = parse_message(topic, payload, resolve_room)
        if reading is None:
            return
        writer.write(reading)

    return handle
