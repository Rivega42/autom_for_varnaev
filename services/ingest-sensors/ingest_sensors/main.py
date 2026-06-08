"""Точка входа воркера ingest-sensors.

Собирает рабочий конвейер приёма показаний:
  MQTT → разбор → запись в БД → сверка с порогами → события в log-service.

Справочник узлов (node_id → room_id) и пороги загружаются из БД при старте.
Контроль «тишины» узлов подключается отдельной задачей (нужен периодический
тик и источник silent_min).
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import Engine, text

from ingest_sensors.db import DbReadingWriter, build_engine
from ingest_sensors.events import HttpEventSink
from ingest_sensors.mqtt import run
from ingest_sensors.parsing import RoomResolver
from ingest_sensors.pipeline import make_reading_handler
from ingest_sensors.thresholds import ThresholdMonitor, load_thresholds

logger = logging.getLogger(__name__)


def _load_node_rooms(engine: Engine) -> dict[str, str]:
    """Загрузить соответствие node_id → room_id из справочника sensor_nodes."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, room_id FROM sensor_nodes")).mappings().all()
    return {row["id"]: row["room_id"] for row in rows}


def main() -> None:
    """Настроить логирование, собрать конвейер и запустить воркер."""
    logging.basicConfig(level=logging.INFO)
    engine = build_engine()

    nodes = _load_node_rooms(engine)
    if not nodes:
        logger.warning("Справочник sensor_nodes пуст — показания узлов будут отброшены")

    def resolve_room(node_id: str) -> str | None:
        return nodes.get(node_id)

    _resolver: RoomResolver = resolve_room

    monitor = ThresholdMonitor(load_thresholds(engine))
    sink = HttpEventSink(os.getenv("LOG_SERVICE_URL", "http://log-service:8000"))
    handler = make_reading_handler(DbReadingWriter(engine), _resolver, monitor=monitor, sink=sink)

    logger.info("ingest-sensors: узлов в справочнике=%d, конвейер собран", len(nodes))
    run(handler=handler)


if __name__ == "__main__":
    main()
