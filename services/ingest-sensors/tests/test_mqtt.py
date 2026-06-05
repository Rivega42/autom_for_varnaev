"""Проверка построения MQTT-клиента (без подключения к брокеру)."""

import paho.mqtt.client as mqtt
from ingest_sensors.config import Settings
from ingest_sensors.mqtt import build_client


def test_build_client_returns_client() -> None:
    """build_client возвращает настроенный клиент без подключения."""
    settings = Settings(
        mqtt_host="localhost",
        mqtt_port=1883,
        mqtt_topic_prefix="monitoring",
        mqtt_username=None,
        mqtt_password=None,
    )
    client = build_client(settings)
    assert isinstance(client, mqtt.Client)
    assert client.on_connect is not None
