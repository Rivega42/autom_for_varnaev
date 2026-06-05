"""Подключение воркера к MQTT-брокеру (paho-mqtt)."""

from __future__ import annotations

import logging
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from ingest_sensors.config import Settings

logger = logging.getLogger(__name__)


def build_client(settings: Settings) -> mqtt.Client:
    """Создать и настроить MQTT-клиент (без подключения) — удобно для тестов."""
    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    client.on_connect = _on_connect
    return client


def _on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: Any,
    reason_code: Any,
    properties: Any = None,
) -> None:
    """Колбэк подключения: логирует результат (сообщения оператору — по-русски)."""
    if reason_code == 0:
        logger.info("Подключение к MQTT-брокеру установлено")
    else:
        logger.warning("Не удалось подключиться к MQTT-брокеру: %s", reason_code)


def run(settings: Settings | None = None) -> None:
    """Запустить воркер: подключиться к брокеру и слушать (блокирующе)."""
    settings = settings or Settings.from_env()
    client = build_client(settings)
    logger.info("Подключение к брокеру %s:%s", settings.mqtt_host, settings.mqtt_port)
    client.connect(settings.mqtt_host, settings.mqtt_port)
    client.loop_forever()
