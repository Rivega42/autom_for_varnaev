"""Проверка формирования события threshold_exceeded и стока событий."""

from datetime import UTC, datetime

from ingest_sensors.events import LoggingEventSink, build_threshold_exceeded

from monitoring_shared import (
    Event,
    EventType,
    Metric,
    Reading,
    Severity,
    Threshold,
    ThresholdOp,
)

_READING = Reading(
    ts=datetime(2026, 6, 5, 10, 30, tzinfo=UTC),
    node_id="node-02",
    room_id="room-02",
    metric=Metric.AIR_TEMP,
    value=8.7,
    unit="C",
)
_THRESHOLD = Threshold(
    id=1,
    room_id=None,
    metric=Metric.AIR_TEMP,
    op=ThresholdOp.GT,
    value=8.0,
    severity=Severity.WARNING,
    silent_min=None,
    enabled=True,
)


def test_build_threshold_exceeded_message_and_fields() -> None:
    """Событие несёт корректные type/severity/payload и русский message."""
    event = build_threshold_exceeded(_READING, _THRESHOLD, lambda _r: "холодильной камере")
    assert event.type is EventType.THRESHOLD_EXCEEDED
    assert event.severity is Severity.WARNING
    assert event.message == "В холодильной камере температура выше нормы"
    assert event.payload["value"] == 8.7
    assert event.payload["threshold"] == 8.0


def test_default_describer_used() -> None:
    """Без описателя в message попадает room_id."""
    event = build_threshold_exceeded(_READING, _THRESHOLD)
    assert "room-02" in event.message


def test_logging_sink_emits() -> None:
    """LoggingEventSink не падает при отправке события."""
    event = build_threshold_exceeded(_READING, _THRESHOLD)
    assert isinstance(event, Event)
    LoggingEventSink().emit(event)  # не должно бросать
