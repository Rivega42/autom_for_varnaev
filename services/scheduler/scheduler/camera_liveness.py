"""Монитор живости камер: проба go2rtc → camera_offline/camera_online (#283).

Вызывается из цикла планировщика на каждом тике. Для каждой включённой камеры
проверяет, отдаёт ли go2rtc её кадр; отвал камеры порождает `camera_offline`
один раз на эпизод, восстановление — `camera_online`. Симметрично «тишине» узла
датчика (`sensor_silent`). Состояние эпизодов живёт в мониторе между тиками.

Если недоступен сам go2rtc, покамерные пробы бессмысленны: вместо лавины
`camera_offline` по всем камерам эмитится один агрегированный сигнал
`media_gateway_offline` (раз на эпизод), при восстановлении —
`media_gateway_online`, и покамерная проверка возобновляется (#286).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Engine

from scheduler.camera_store import CameraProber, load_enabled_cameras
from scheduler.events import (
    EventSink,
    build_camera_offline,
    build_camera_online,
    build_media_gateway_offline,
    build_media_gateway_online,
)

logger = logging.getLogger(__name__)


class CameraLivenessMonitor:
    """Проверка доступности камер с памятью «упавших» между тиками.

    Проба синхронная и последовательная: суммарно N камер × таймаут пробы должно
    укладываться в `tick_interval_s` планировщика (по умолчанию 3 c × несколько
    камер ≪ 60 c). Пока go2rtc недоступен целиком, камеры не пробуются, а их
    эпизоды заморожены: упавшие до отвала шлюза камеры не «восстанавливаются»,
    новые `camera_offline` не порождаются — действует агрегированный сигнал.
    """

    def __init__(self, sink: EventSink, prober: CameraProber) -> None:
        self._sink = sink
        self._prober = prober
        # id камер, по которым уже сообщили об отвале (ждём восстановления).
        self._offline: set[str] = set()
        # эпизод недоступности самого медиа-шлюза (#286)
        self._gateway_down = False

    def check(self, engine: Engine, now: datetime) -> int:
        """Один проход: проверить шлюз и все включённые камеры; вернуть число событий."""
        emitted = 0
        if not self._prober.is_gateway_up():
            if not self._gateway_down:
                self._sink.emit(build_media_gateway_offline(now))
                self._gateway_down = True
                emitted += 1
                logger.warning("Медиа-шлюз (go2rtc) недоступен — камеры не проверяются")
            return emitted
        if self._gateway_down:
            self._sink.emit(build_media_gateway_online(now))
            self._gateway_down = False
            emitted += 1
            logger.info("Медиа-шлюз (go2rtc) снова на связи")
        seen: set[str] = set()
        for cam in load_enabled_cameras(engine):
            seen.add(cam.id)
            live = self._prober.is_live(cam.name)
            if not live and cam.id not in self._offline:
                self._sink.emit(build_camera_offline(cam, now))
                self._offline.add(cam.id)
                emitted += 1
                logger.warning("Камера «%s» не отвечает", cam.name)
            elif live and cam.id in self._offline:
                self._sink.emit(build_camera_online(cam, now))
                self._offline.discard(cam.id)
                emitted += 1
                logger.info("Камера «%s» снова на связи", cam.name)
        # Камеры, выбывшие из справочника пока были offline, забываем без события.
        self._offline &= seen
        return emitted
