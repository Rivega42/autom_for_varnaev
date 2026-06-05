"""Конфигурация воркера ingest-sensors из переменных окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Параметры подключения воркера."""

    mqtt_host: str
    mqtt_port: int
    mqtt_topic_prefix: str
    mqtt_username: str | None
    mqtt_password: str | None

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения (значения по умолчанию — как в compose)."""
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", "mqtt-broker"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_topic_prefix=os.getenv("MQTT_TOPIC_PREFIX", "monitoring"),
            mqtt_username=os.getenv("MQTT_USERNAME") or None,
            mqtt_password=os.getenv("MQTT_PASSWORD") or None,
        )
