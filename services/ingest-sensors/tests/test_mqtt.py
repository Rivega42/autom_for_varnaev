"""Проверка построения клиента и маршрутизации сообщений (без брокера)."""

import paho.mqtt.client as mqtt
from ingest_sensors.config import Settings
from ingest_sensors.mqtt import build_client

_SETTINGS = Settings(
    mqtt_host="localhost",
    mqtt_port=1883,
    mqtt_topic_prefix="monitoring",
    mqtt_username=None,
    mqtt_password=None,
)


def test_build_client_returns_client() -> None:
    """build_client возвращает настроенный клиент без подключения."""
    client = build_client(_SETTINGS)
    assert isinstance(client, mqtt.Client)
    assert client.on_connect is not None
    assert client.on_message is not None


def test_on_message_routes_to_handler() -> None:
    """Входящее сообщение направляется в переданный обработчик."""
    received: list[tuple[str, bytes]] = []

    def handler(topic: str, payload: bytes) -> None:
        received.append((topic, payload))

    client = build_client(_SETTINGS, handler)

    message = mqtt.MQTTMessage(topic=b"monitoring/node-01/air_temp")
    message.payload = b'{"value": 8.7}'

    on_message = client.on_message
    assert on_message is not None
    on_message(client, None, message)  # эмуляция доставки сообщения

    assert received == [("monitoring/node-01/air_temp", b'{"value": 8.7}')]
