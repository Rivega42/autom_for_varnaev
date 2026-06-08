"""Точка входа воркера ingest-sensors.

Собирает рабочий конвейер приёма показаний:
  MQTT → разбор → запись в БД → сверка с порогами → события в log-service.

Справочник узлов (node_id → room_id) и пороги загружаются из БД. Пороги
перечитываются каждый тик (правки порогов через интерфейс применяются без
рестарта); справочник узлов читается один раз на старте — добавление нового
узла требует перезапуска воркера. Периодический тик также проверяет «тишину»
узлов (событие sensor_silent), порог тишины берётся из thresholds.silent_min.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import Engine, text

from ingest_sensors.db import DbReadingWriter, build_engine
from ingest_sensors.events import HttpEventSink
from ingest_sensors.mqtt import run
from ingest_sensors.parsing import RoomResolver
from ingest_sensors.pipeline import make_reading_handler
from ingest_sensors.silence_tracker import SilenceTracker
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

    # Контроль «тишины» узлов: порог берётся из thresholds.silent_min помещения
    # (docs/08, docs/04 §4). Если для помещения порог не задан — общий запасной
    # из env. Резолвер читает актуальные пороги монитора (горячая перезагрузка).
    default_silent_min = int(os.getenv("SENSOR_SILENT_MIN", "10"))

    def silent_min_for_room(room_id: str | None) -> int:
        return monitor.silent_min_for(room_id, default_silent_min)

    silence = SilenceTracker(sink, _resolver, silent_min_for_room)

    handler = make_reading_handler(
        DbReadingWriter(engine),
        _resolver,
        monitor=monitor,
        sink=sink,
        on_reading=silence.record,
    )

    def on_tick() -> None:
        # Горячая перезагрузка порогов (изменения из интерфейса) + проверка тишины.
        try:
            monitor.replace(load_thresholds(engine))
        except Exception:
            logger.exception("Не удалось перечитать пороги из БД")
        silence.check(datetime.now(UTC))

    logger.info(
        "ingest-sensors: узлов=%d, запасной порог тишины=%d мин, конвейер собран",
        len(nodes),
        default_silent_min,
    )
    run(handler=handler, on_tick=on_tick)


if __name__ == "__main__":
    main()
