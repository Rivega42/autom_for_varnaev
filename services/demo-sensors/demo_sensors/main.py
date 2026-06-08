"""Демо-публикатор синтетических показаний датчиков в MQTT (демо-режим).

Подключается к брокеру и периодически публикует показания на топики
<prefix>/<node>/<metric>, которые принимает ingest-sensors. Раз в несколько
тиков выдаёт аномальные значения, чтобы сработали пороги и появились события.
Запускается только демо-оверлеем (docker-compose.demo.yml), не в боевом стеке.
"""

from __future__ import annotations

import logging
import os
import random
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from demo_sensors.generator import default_nodes, reading_payload, reading_topic, synth_value

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Прочитать целочисленную переменную окружения с запасным значением."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def run() -> None:
    """Бесконечный цикл публикации синтетических показаний в MQTT."""
    host = os.getenv("MQTT_HOST", "mqtt-broker")
    port = _env_int("MQTT_PORT", 1883)
    prefix = os.getenv("MQTT_TOPIC_PREFIX", "monitoring")
    interval = _env_int("DEMO_INTERVAL_S", 5)
    # Каждый N-й тик — «всплеск» (0 = без всплесков). По умолчанию ~раз в минуту.
    spike_every = _env_int("DEMO_SPIKE_EVERY", 12)

    nodes = default_nodes()
    rng = random.Random()

    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    username = os.getenv("MQTT_USERNAME")
    if username:
        client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
    client.connect(host, port)
    client.loop_start()
    logger.info("Демо-генератор показаний запущен: %s:%d, интервал %d с", host, port, interval)

    step = 0
    try:
        while True:
            spike = spike_every > 0 and step > 0 and step % spike_every == 0
            for node in nodes:
                for profile in node.metrics:
                    value = synth_value(profile, step=step, rng=rng, spike=spike)
                    topic = reading_topic(prefix, node.node_id, profile.metric)
                    client.publish(topic, reading_payload(profile.metric, value))
            if spike:
                logger.info("Демо-всплеск (шаг %d): аномальные значения для проверки порогов", step)
            step += 1
            time.sleep(interval)
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> None:
    """Точка входа: настроить логирование и запустить цикл публикации."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()
