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


def test_per_room_silent_min_resolver() -> None:
    """Порог тишины может зависеть от помещения узла (функция-резолвер)."""
    sink = _CollectingSink()
    rooms = {"cold-01": "cold-01", "room-02": "room-02"}
    # Холодильная камера — строгий порог 5 мин, обычное помещение — 20 мин.
    silent_min_for = {"cold-01": 5, "room-02": 20}.get
    tracker = SilenceTracker(sink, rooms.get, lambda room: silent_min_for(room, 10) if room else 10)
    t0 = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)
    tracker.record(_reading_in("cold-01", t0))
    tracker.record(_reading_in("room-02", t0))

    # Через 7 минут: холодильная камера уже молчит (порог 5), обычная — нет (порог 20).
    assert tracker.check(t0 + timedelta(minutes=7)) == 1
    assert [e.payload["node_id"] for e in sink.events] == ["cold-01"]


def _reading_in(node_id: str, ts: datetime) -> Reading:
    return Reading(
        ts=ts, node_id=node_id, room_id=node_id, metric=Metric.AIR_TEMP, value=4.0, unit="C"
    )


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
