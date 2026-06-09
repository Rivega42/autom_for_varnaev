"""Конфигурация воркера video-analytics из окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Параметры воркера."""

    log_service_url: str
    artifacts_dir: str
    fps: int
    # Лимит кадров для live-потока (stream): один прогон анализа читает не больше
    # этого числа кадров, затем считает покрытие и завершается. RTSP бесконечен,
    # без лимита задание висит вечно. Для file не применяется (читаем весь файл).
    max_stream_frames: int = 150

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения."""
        return cls(
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            artifacts_dir=os.getenv("ARTIFACTS_DIR", "/data/artifacts"),
            fps=int(os.getenv("ANALYTICS_FPS", "5")),
            max_stream_frames=int(os.getenv("ANALYTICS_MAX_STREAM_FRAMES", "150")),
        )
