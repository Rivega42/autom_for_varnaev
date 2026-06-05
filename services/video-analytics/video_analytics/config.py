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

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения."""
        return cls(
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            artifacts_dir=os.getenv("ARTIFACTS_DIR", "/data/artifacts"),
            fps=int(os.getenv("ANALYTICS_FPS", "5")),
        )
