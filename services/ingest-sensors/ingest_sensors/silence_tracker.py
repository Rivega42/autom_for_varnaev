"""Отслеживание «тишины» узлов и эмиссия событий sensor_silent.

Связывает SilenceMonitor со стоком событий: фиксирует активность узла на каждом
показании (`record`) и периодически (`check`) эмитит событие о молчании узла
дольше `silent_min`. Потокобезопасен: `record` вызывается из сетевого потока
MQTT, а `check` — из основного потока (периодический тик).
"""

from __future__ import annotations

import threading
from datetime import datetime

from ingest_sensors.events import (
    EventSink,
    RoomDescriber,
    build_sensor_silent,
    default_room_describer,
)
from ingest_sensors.parsing import RoomResolver
from ingest_sensors.silence import SilenceMonitor
from monitoring_shared import Reading


class SilenceTracker:
    """Фиксирует активность узлов и эмитит sensor_silent при молчании."""

    def __init__(
        self,
        sink: EventSink,
        resolve_room: RoomResolver,
        silent_min: int,
        *,
        monitor: SilenceMonitor | None = None,
        describe_room: RoomDescriber = default_room_describer,
    ) -> None:
        self._sink = sink
        self._resolve_room = resolve_room
        self._silent_min = silent_min
        self._monitor = monitor or SilenceMonitor()
        self._describe_room = describe_room
        self._lock = threading.Lock()

    def record(self, reading: Reading) -> None:
        """Отметить активность узла по показанию (сбрасывает признак тишины)."""
        with self._lock:
            self._monitor.record(reading.node_id, reading.ts)

    def check(self, now: datetime) -> int:
        """Проверить тишину и эмитить sensor_silent; вернуть число событий."""
        with self._lock:
            silent = self._monitor.silent_nodes(now, self._silent_min)
        for node_id, elapsed_min in silent:
            self._sink.emit(
                build_sensor_silent(
                    node_id,
                    self._resolve_room(node_id),
                    elapsed_min,
                    now,
                    self._describe_room,
                )
            )
        return len(silent)
