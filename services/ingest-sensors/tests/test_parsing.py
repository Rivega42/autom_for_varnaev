"""Проверка разбора MQTT-сообщений в Reading."""

from datetime import UTC, datetime

from ingest_sensors.parsing import parse_message

from monitoring_shared import Metric

# Простой резолвер помещений для тестов.
_ROOMS = {"node-01": "room-01"}


def _resolve(node_id: str) -> str | None:
    return _ROOMS.get(node_id)


def test_parse_valid_message() -> None:
    """Корректное сообщение разбирается в Reading со всеми полями."""
    reading = parse_message(
        "monitoring/node-01/air_temp",
        b'{"value": 8.7, "unit": "C", "ts": "2026-06-05T10:30:00+00:00"}',
        _resolve,
    )
    assert reading is not None
    assert reading.node_id == "node-01"
    assert reading.room_id == "room-01"
    assert reading.metric is Metric.AIR_TEMP
    assert reading.value == 8.7
    assert reading.unit == "C"
    assert reading.ts == datetime(2026, 6, 5, 10, 30, tzinfo=UTC)


def test_parse_without_ts_uses_now() -> None:
    """Без ts берётся время приёма (ts заполнен)."""
    reading = parse_message("monitoring/node-01/humidity", b'{"value": 41, "unit": "%"}', _resolve)
    assert reading is not None
    assert reading.ts is not None


def test_parse_unknown_metric_returns_none() -> None:
    """Нераспознанная метрика → None."""
    assert parse_message("monitoring/node-01/co2", b'{"value": 1, "unit": "ppm"}', _resolve) is None


def test_parse_bad_json_returns_none() -> None:
    """Битый JSON → None."""
    assert parse_message("monitoring/node-01/air_temp", b"not-json", _resolve) is None


def test_parse_missing_fields_returns_none() -> None:
    """Отсутствие value/unit → None."""
    assert parse_message("monitoring/node-01/air_temp", b'{"value": 8.7}', _resolve) is None


def test_parse_unknown_node_returns_none() -> None:
    """Неизвестный узел (резолвер вернул None) → None."""
    assert (
        parse_message("monitoring/node-99/air_temp", b'{"value": 8.7, "unit": "C"}', _resolve)
        is None
    )
