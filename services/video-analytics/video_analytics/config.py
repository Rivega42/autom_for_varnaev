"""Конфигурация воркера video-analytics из окружения."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_MAX_STREAM_FRAMES = 150


@dataclass(frozen=True)
class Settings:
    """Параметры воркера."""

    log_service_url: str
    artifacts_dir: str
    fps: int
    # Лимит кадров для live-потока (stream): один прогон анализа читает не больше
    # этого числа кадров, затем считает покрытие и завершается. RTSP бесконечен,
    # без лимита задание висит вечно. Для file не применяется (читаем весь файл).
    max_stream_frames: int = _DEFAULT_MAX_STREAM_FRAMES
    # Путь к модели MediaPipe PoseLandmarker (бинарный ассет на томе /models).
    model_path: str = "/models/pose_landmarker.task"

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения."""
        max_frames = int(os.getenv("ANALYTICS_MAX_STREAM_FRAMES", str(_DEFAULT_MAX_STREAM_FRAMES)))
        if max_frames <= 0:
            # 0/отрицательное значение сняло бы лимит и подвесило воркер на живом
            # RTSP навсегда — трактуем как ошибку конфигурации и берём дефолт.
            logger.warning(
                "ANALYTICS_MAX_STREAM_FRAMES=%s некорректно (лимит обязателен для "
                "stream) — использую %s",
                max_frames,
                _DEFAULT_MAX_STREAM_FRAMES,
            )
            max_frames = _DEFAULT_MAX_STREAM_FRAMES
        return cls(
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            artifacts_dir=os.getenv("ARTIFACTS_DIR", "/data/artifacts"),
            fps=int(os.getenv("ANALYTICS_FPS", "5")),
            max_stream_frames=max_frames,
            model_path=os.getenv("ANALYTICS_MODEL_PATH", "/models/pose_landmarker.task"),
        )
