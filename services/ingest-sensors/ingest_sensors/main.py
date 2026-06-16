"""Точка входа воркера ingest-sensors.

Собирает рабочий конвейер приёма показаний:
  MQTT → разбор → запись в БД → сверка с порогами → события в log-service.

Справочник узлов (node_id → room_id) и пороги загружаются из БД и
**перечитываются каждый тик** (правки через интерфейс применяются без рестарта):
пороги — ThresholdMonitor, узлы — NodeRegistry (#355), поэтому узел, заведённый
на работающем стеке, подхватывается без перезапуска воркера. Периодический тик
также проверяет «тишину» узлов (событие sensor_silent), порог тишины берётся из
thresholds.silent_min.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from ingest_sensors.db import DbReadingWriter, build_engine, write_heartbeat
from ingest_sensors.events import HttpEventSink
from ingest_sensors.mqtt import run
from ingest_sensors.node_registry import NodeRegistry
from ingest_sensors.parsing import RoomResolver
from ingest_sensors.pipeline import make_reading_handler
from ingest_sensors.silence_tracker import SilenceTracker
from ingest_sensors.thresholds import ThresholdMonitor, load_thresholds
from monitoring_shared import install_stop_event

logger = logging.getLogger(__name__)


def main() -> None:
    """Настроить логирование, собрать конвейер и запустить воркер."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    engine = build_engine()

    registry = NodeRegistry(engine)
    if len(registry) == 0:
        logger.warning("Справочник sensor_nodes пуст — показания узлов будут отброшены")

    _resolver: RoomResolver = registry.resolve

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
        # Отметка живости сервиса (watchdog, #284) + горячая перезагрузка порогов
        # и справочника узлов (изменения из интерфейса) + проверка тишины узлов.
        write_heartbeat(engine, "ingest-sensors", datetime.now(UTC))
        try:
            monitor.replace(load_thresholds(engine))
        except Exception:
            logger.exception("Не удалось перечитать пороги из БД")
        try:
            registry.refresh()  # #355: новые узлы подхватываются без рестарта
        except Exception:
            logger.exception("Не удалось перечитать справочник узлов из БД")
        silence.check(datetime.now(UTC))

    logger.info(
        "ingest-sensors: узлов=%d, запасной порог тишины=%d мин, конвейер собран",
        len(registry),
        default_silent_min,
    )
    # Мягкая остановка по SIGTERM/SIGINT (#206): docker stop отключает клиента
    # от брокера штатно, engine закрывается в finally.
    stop = install_stop_event()
    try:
        run(handler=handler, on_tick=on_tick, stop_event=stop)
    finally:
        engine.dispose()
        logger.info("ingest-sensors остановлен штатно")


if __name__ == "__main__":
    main()
