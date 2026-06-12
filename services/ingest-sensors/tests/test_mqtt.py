"""Проверка построения клиента и маршрутизации сообщений (без брокера)."""

import threading
from typing import cast

import paho.mqtt.client as mqtt
from ingest_sensors.config import Settings
from ingest_sensors.mqtt import MessageHandler, build_client, run

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


class _FakeClient:
    """Клиент-заглушка: фиксирует последовательность вызовов жизненного цикла."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        self.calls.append("reconnect_delay_set")

    def connect(self, host: str, port: int) -> None:
        self.calls.append("connect")

    def loop_start(self) -> None:
        self.calls.append("loop_start")

    def loop_stop(self) -> None:
        self.calls.append("loop_stop")

    def disconnect(self) -> None:
        self.calls.append("disconnect")


def test_run_stops_on_stop_event() -> None:
    """Взведённый stop_event: run() выходит из цикла и штатно отключается (#206)."""
    fake = _FakeClient()

    def factory(settings: Settings, handler: MessageHandler | None) -> mqtt.Client:
        return cast(mqtt.Client, fake)

    stop = threading.Event()
    stop.set()
    run(_SETTINGS, None, stop_event=stop, client_factory=factory)

    # DISCONNECT уходит до остановки сетевого потока (порядок важен).
    assert fake.calls == ["reconnect_delay_set", "connect", "loop_start", "disconnect", "loop_stop"]
