"""Точка входа воркера video-analytics: цикл обработки заданий из очереди.

Процесс в цикле берёт задания (`analysis_tasks`) и обрабатывает их; при пустой
очереди ждёт `idle_sleep_s` секунд. Тяжёлые зависимости (MediaPipe, OpenCV)
создаются только в `main()` — в тестах используется `worker.run_once` с фейками.
Запуск: `python -m video_analytics.main`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine

from monitoring_shared import SourceType
from video_analytics.capture import create_frame_source
from video_analytics.config import Settings
from video_analytics.db import build_engine
from video_analytics.detector import MediaPipePoseDetector, PoseDetector
from video_analytics.event_sink import EventSink, HttpEventSink
from video_analytics.sources import FrameSource
from video_analytics.worker import SourceFactory, run_once

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


def _default_source_factory(
    source_type: SourceType, source_ref: str, target_fps: int
) -> FrameSource:
    """Боевая фабрика источника кадров (stream|file) с понижением до target_fps."""
    return create_frame_source(source_type, source_ref, target_fps=target_fps)


def run_forever(
    engine: Engine,
    settings: Settings,
    *,
    detector: PoseDetector,
    sink: EventSink,
    source_factory: SourceFactory,
    sleep: Callable[[float], None] = time.sleep,
    idle_sleep_s: float = 5.0,
    now_fn: Callable[[], datetime] = _now_utc,
    max_iterations: int | None = None,
) -> None:
    """Цикл воркера: обрабатывать задания, при пустой очереди ждать `idle_sleep_s`.

    `max_iterations` ограничивает число итераций (для тестов); при `None` цикл
    бесконечный.
    """
    iteration = 0
    while True:
        processed = run_once(
            engine,
            settings,
            detector=detector,
            sink=sink,
            source_factory=source_factory,
            now_fn=now_fn,
        )
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            return
        if not processed:
            sleep(idle_sleep_s)


def main() -> None:
    """Собрать боевые зависимости (БД, детектор, сток) и запустить цикл."""
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    engine = build_engine()
    model_path = os.getenv("ANALYTICS_MODEL_PATH", "/models/pose_landmarker.task")
    detector = MediaPipePoseDetector(model_path)
    sink = HttpEventSink(settings.log_service_url)
    logger.info(
        "Видеоаналитика запущена: модель=%s, лог=%s",
        model_path,
        settings.log_service_url,
    )
    run_forever(
        engine,
        settings,
        detector=detector,
        sink=sink,
        source_factory=_default_source_factory,
    )


if __name__ == "__main__":
    main()
