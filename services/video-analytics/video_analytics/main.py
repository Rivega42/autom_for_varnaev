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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine

from monitoring_shared import SourceType, install_stop_event
from video_analytics.aura_callback import AuraNotifier
from video_analytics.capture import create_frame_source
from video_analytics.config import Settings
from video_analytics.db import build_engine, write_heartbeat
from video_analytics.detector import MediaPipePoseDetector, PoseDetector
from video_analytics.event_sink import EventSink, HttpEventSink
from video_analytics.retention import cleanup_artifacts
from video_analytics.sources import FrameSource
from video_analytics.worker import SourceFactory, run_once

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


def _make_source_factory(settings: Settings) -> SourceFactory:
    """Боевая фабрика источника кадров с понижением fps и лимитом кадров для stream."""

    def factory(source_type: SourceType, source_ref: str, target_fps: int) -> FrameSource:
        return create_frame_source(
            source_type,
            source_ref,
            target_fps=target_fps,
            max_frames=settings.max_stream_frames,
        )

    return factory


def run_forever(
    engine: Engine,
    settings: Settings,
    *,
    detector: PoseDetector,
    sink: EventSink,
    source_factory: SourceFactory,
    # object, а не None: сюда удобно передавать Event.wait (возвращает bool).
    sleep: Callable[[float], object] = time.sleep,
    idle_sleep_s: float = 5.0,
    now_fn: Callable[[], datetime] = _now_utc,
    max_iterations: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """Цикл воркера: обрабатывать задания, при пустой очереди ждать `idle_sleep_s`.

    `max_iterations` ограничивает число итераций (для тестов); при `None` цикл
    бесконечный. `should_stop` — мягкая остановка (#206): проверяется перед
    каждой итерацией, текущее задание не прерывается. Раз в сутки (и при старте)
    выполняется ротация артефактов: скриншоты старше `artifacts_retention_days`
    удаляются вместе со строками.
    """
    iteration = 0
    next_cleanup = now_fn()  # первая зачистка — сразу при старте
    # D.5 (#350): отправитель уведомлений АУРА о готовности задания (best-effort,
    # один httpx-клиент на жизнь воркера). Срабатывает только если у задания есть
    # callback_url; иначе ничего не шлёт.
    notifier = AuraNotifier(
        timeout=settings.aura_callback_timeout_s,
        retries=settings.aura_callback_retries,
        allowed_hosts=settings.aura_callback_allowed_hosts,
    )
    while True:
        if should_stop is not None and should_stop():
            logger.info("Видеоаналитика: получен сигнал остановки — выходим из цикла")
            return
        # Отметка живости (#284). Пишется между заданиями: SERVICE_SILENT_MIN
        # должен превышать длительность самого долгого одиночного run_once
        # (окно анализа ограничено ANALYTICS_MAX_STREAM_FRAMES, обычно ≈30 c).
        write_heartbeat(engine, "video-analytics", now_fn())
        if settings.artifacts_retention_days > 0 and now_fn() >= next_cleanup:
            try:
                cleanup_artifacts(
                    engine,
                    settings.artifacts_dir,
                    retention_days=settings.artifacts_retention_days,
                    now=now_fn(),
                )
            except Exception:
                # Сбой ротации не должен останавливать обработку заданий.
                logger.exception("Сбой ротации артефактов — продолжаю работу")
            next_cleanup = now_fn() + timedelta(days=1)
        processed = run_once(
            engine,
            settings,
            detector=detector,
            sink=sink,
            source_factory=source_factory,
            now_fn=now_fn,
            notifier=notifier,
        )
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            return
        if not processed:
            sleep(idle_sleep_s)


def main() -> None:
    """Собрать боевые зависимости (БД, детектор, сток) и запустить цикл."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    settings = Settings.from_env()
    # Понятная диагностика вместо трудночитаемого падения MediaPipe (#206):
    # модель — бинарный ассет, его кладут на объект отдельно (models/README.md).
    if not Path(settings.model_path).is_file():
        logger.error(
            "Файл модели MediaPipe не найден: %s — положите pose_landmarker.task "
            "в ./models (bash scripts/fetch_model.sh, см. models/README.md) или "
            "задайте путь переменной ANALYTICS_MODEL_PATH",
            settings.model_path,
        )
        raise SystemExit(1)
    engine = build_engine()
    detector = MediaPipePoseDetector(settings.model_path)
    sink = HttpEventSink(settings.log_service_url)
    logger.info(
        "Видеоаналитика запущена: модель=%s, лог=%s",
        settings.model_path,
        settings.log_service_url,
    )
    # Мягкая остановка по SIGTERM/SIGINT (#206): docker stop завершает цикл
    # между заданиями, сон прерывается сразу (sleep = stop.wait).
    stop = install_stop_event()
    try:
        run_forever(
            engine,
            settings,
            detector=detector,
            sink=sink,
            source_factory=_make_source_factory(settings),
            sleep=stop.wait,
            should_stop=stop.is_set,
        )
    finally:
        engine.dispose()
        logger.info("Видеоаналитика остановлена штатно")


if __name__ == "__main__":
    main()
