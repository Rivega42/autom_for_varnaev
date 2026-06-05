"""Проверка конфигурации воркера из окружения."""

import pytest
from ingest_sensors.config import Settings


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Настройки читаются из переменных окружения."""
    monkeypatch.setenv("MQTT_HOST", "broker.local")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("MQTT_TOPIC_PREFIX", "mon")
    monkeypatch.delenv("MQTT_USERNAME", raising=False)
    settings = Settings.from_env()
    assert settings.mqtt_host == "broker.local"
    assert settings.mqtt_port == 8883
    assert settings.mqtt_topic_prefix == "mon"
    assert settings.mqtt_username is None
