"""Проверка Pydantic-моделей справочников и показаний."""

from datetime import UTC, datetime

from monitoring_shared import Metric, Reading, Room, SensorNode


def test_room_defaults() -> None:
    """is_cold по умолчанию False."""
    room = Room(id="room-01", name="Кухня")
    assert room.is_cold is False


def test_sensor_node_optional_fields() -> None:
    """Необязательные поля узла по умолчанию None."""
    node = SensorNode(id="node-01", room_id="room-01")
    assert node.placement is None
    assert node.power is None


def test_reading_metric_enum() -> None:
    """Показание принимает метрику из перечисления."""
    reading = Reading(
        ts=datetime(2026, 6, 5, 10, 30, tzinfo=UTC),
        node_id="node-01",
        room_id="room-01",
        metric=Metric.AIR_TEMP,
        value=8.7,
        unit="C",
    )
    assert reading.metric is Metric.AIR_TEMP
    assert reading.value == 8.7
