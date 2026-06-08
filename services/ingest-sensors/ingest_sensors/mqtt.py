"""Подключение воркера к MQTT-брокеру и подписка на показания (paho-mqtt)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from ingest_sensors.config import Settings

logger = logging.getLogger(__name__)

# Обработчик входящего сообщения: (topic, payload) -> None.
MessageHandler = Callable[[str, bytes], None]
# Периодический тик (например, проверка «тишины» узлов).
TickHandler = Callable[[], None]


def _default_handler(topic: str, payload: bytes) -> None:
    """Обработчик по умолчанию: логирует факт получения (парсинг — в E2.5)."""
    logger.info("Получено сообщение в топике %s (%d байт)", topic, len(payload))


def build_client(settings: Settings, handler: MessageHandler | None = None) -> mqtt.Client:
    """Создать и настроить MQTT-клиент (без подключения) — удобно для тестов.

    Клиент при подключении подписывается на показания `<prefix>/<node>/<metric>`
    и направляет каждое сообщение в `handler`.
    """
    handler = handler or _default_handler
    topic = f"{settings.mqtt_topic_prefix}/+/+"

    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    def on_connect(
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        """Подписаться на топик показаний при успешном подключении."""
        if reason_code == 0:
            client.subscribe(topic)
            logger.info("Подключение установлено, подписка на топик %s", topic)
        else:
            logger.warning("Не удалось подключиться к MQTT-брокеру: %s", reason_code)

    def on_message(client: mqtt.Client, userdata: Any, message: Any) -> None:
        """Передать входящее сообщение в обработчик."""
        handler(message.topic, message.payload)

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def run(
    settings: Settings | None = None,
    handler: MessageHandler | None = None,
    *,
    on_tick: TickHandler | None = None,
    tick_interval_s: float = 60.0,
) -> None:
    """Запустить воркер: подключиться к брокеру и слушать (блокирующе).

    Если задан `on_tick`, сеть обслуживается фоновым потоком (loop_start), а в
    основном потоке периодически (раз в `tick_interval_s` сек) вызывается `on_tick`
    — это используется для проверки «тишины» узлов независимо от входящих
    сообщений. Без `on_tick` поведение прежнее (loop_forever).
    """
    settings = settings or Settings.from_env()
    client = build_client(settings, handler)
    # Автопереподключение с экспоненциальной задержкой (обрыв сети — норма).
    client.reconnect_delay_set(min_delay=1, max_delay=32)
    logger.info("Подключение к брокеру %s:%s", settings.mqtt_host, settings.mqtt_port)
    client.connect(settings.mqtt_host, settings.mqtt_port)

    if on_tick is None:
        client.loop_forever()
        return

    client.loop_start()
    try:
        while True:
            time.sleep(tick_interval_s)
            try:
                on_tick()
            except Exception:
                logger.exception("Ошибка периодической проверки (тик)")
    finally:
        client.loop_stop()
