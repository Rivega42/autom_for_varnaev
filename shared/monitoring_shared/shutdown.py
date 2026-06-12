"""Мягкая остановка воркеров: Event, взводимый по SIGTERM/SIGINT (#206).

`docker stop` шлёт контейнеру SIGTERM и ждёт 10 секунд до SIGKILL. Без
обработчика процесс умирает посреди итерации; с ним — цикл воркера замечает
взведённый Event, дозавершает текущий шаг и выходит штатно (finally закрывает
engine/клиентов).
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

logger = logging.getLogger(__name__)


def install_stop_event() -> threading.Event:
    """Вернуть Event, взводимый по SIGTERM/SIGINT.

    Вызывать в главном потоке процесса (ограничение модуля signal). Удобно
    передавать `event.wait` как `sleep` в цикл воркера: сон прерывается сразу
    при получении сигнала, а `event.is_set` служит признаком остановки.
    """
    stop = threading.Event()

    def _handle(signum: int, frame: FrameType | None) -> None:
        logger.info("Получен сигнал %s — мягкая остановка", signal.Signals(signum).name)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle)
    return stop
