"""Конфигурация api-gateway из переменных окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Параметры внешнего шлюза."""

    # Базовый URL внутреннего log-service (источник событий).
    log_service_url: str
    # API-ключ для публичных и /integration/* эндпойнтов (X-API-Key).
    api_key: str | None
    # СТЫК-АУРА (v2): фичефлаг интеграции; в v1 всегда False (разъёмы отдают 501).
    aura_integration_enabled: bool
    # Базовый URL медиа-шлюза go2rtc (для кадра-превью камеры в GUI разметки ROI).
    go2rtc_url: str = "http://media-gateway:1984"
    # Каталог артефактов-доказательств (общий том со воркером). Из него отдаются
    # стоп-кадры/overlay в Grafana и сюда же кладутся снимки браузерного анализа.
    artifacts_dir: str = "/data/artifacts"

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения (значения по умолчанию — как в compose)."""
        return cls(
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            api_key=os.getenv("API_KEY") or None,
            aura_integration_enabled=os.getenv("AURA_INTEGRATION_ENABLED", "false").lower()
            == "true",
            go2rtc_url=os.getenv("GO2RTC_URL", "http://media-gateway:1984"),
            artifacts_dir=os.getenv("ARTIFACTS_DIR", "/data/artifacts"),
        )
