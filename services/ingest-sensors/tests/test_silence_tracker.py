"""Проверка SilenceTracker: фиксация активности и эмиссия sensor_silent."""

from datetime import UTC, datetime, timedelta

from ingest_sensors.silence_tracker import SilenceTracker

from monitoring_shared import Event, EventType, Metric, Reading


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def _reading(node_id: str, ts: datetime) -> Reading:
    return Reading(
        ts=ts, node_id=node_id, room_id="room-01", metric=Metric.AIR_TEMP, value=4.0, unit="C"
    )


def test_no_event_before_silent_threshold() -> None:
    """Узел активен — события тишины нет."""
    sink = _CollectingSink()
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10)
    t0 = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    tracker.record(_reading("node-01", t0))

    assert tracker.check(t0 + timedelta(minutes=5)) == 0
    assert sink.events == []


def test_emits_sensor_silent_once_after_threshold() -> None:
    """Молчание дольше порога эмитит sensor_silent однократно на эпизод."""
    sink = _CollectingSink()
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10)
    t0 = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    tracker.record(_reading("node-01", t0))

    assert tracker.check(t0 + timedelta(minutes=12)) == 1
    assert tracker.check(t0 + timedelta(minutes=20)) == 0  # повторно не дублируется

    assert [e.type for e in sink.events] == [EventType.SENSOR_SILENT]
    assert sink.events[0].payload["node_id"] == "node-01"


def test_record_resets_silence() -> None:
    """Новое показание сбрасывает эпизод тишины — событие может прийти снова."""
    sink = _CollectingSink()
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10)
    t0 = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    tracker.record(_reading("node-01", t0))
    tracker.check(t0 + timedelta(minutes=12))  # первое событие

    tracker.record(_reading("node-01", t0 + timedelta(minutes=15)))  # узел снова жив
    assert tracker.check(t0 + timedelta(minutes=30)) == 1  # снова замолчал
    assert len(sink.events) == 2
