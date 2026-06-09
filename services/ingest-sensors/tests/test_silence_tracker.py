"""Проверка SilenceTracker: фиксация активности и эмиссия sensor_silent.

Активность узла фиксируется СЕРВЕРНЫМИ часами (now_fn), а не временем с часов
узла (reading.ts): сдвиг часов ESP32 не должен давать ложные sensor_silent.
В тестах часы инъектируются (_Clock).
"""

from datetime import UTC, datetime, timedelta

from ingest_sensors.silence_tracker import SilenceTracker

from monitoring_shared import Event, EventType, Metric, Reading


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _Clock:
    """Управляемые серверные часы для тестов."""

    def __init__(self, t: datetime) -> None:
        self.t = t

    def now(self) -> datetime:
        return self.t


def _reading(node_id: str, ts: datetime) -> Reading:
    return Reading(
        ts=ts, node_id=node_id, room_id="room-01", metric=Metric.AIR_TEMP, value=4.0, unit="C"
    )


def _reading_in(node_id: str, ts: datetime) -> Reading:
    return Reading(
        ts=ts, node_id=node_id, room_id=node_id, metric=Metric.AIR_TEMP, value=4.0, unit="C"
    )


T0 = datetime(2026, 6, 8, 10, 0, tzinfo=UTC)


def test_no_event_before_silent_threshold() -> None:
    """Узел активен — события тишины нет."""
    sink = _CollectingSink()
    clock = _Clock(T0)
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10, now_fn=clock.now)
    tracker.record(_reading("node-01", T0))

    assert tracker.check(T0 + timedelta(minutes=5)) == 0
    assert sink.events == []


def test_emits_sensor_silent_once_after_threshold() -> None:
    """Молчание дольше порога эмитит sensor_silent однократно на эпизод."""
    sink = _CollectingSink()
    clock = _Clock(T0)
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10, now_fn=clock.now)
    tracker.record(_reading("node-01", T0))

    assert tracker.check(T0 + timedelta(minutes=12)) == 1
    assert tracker.check(T0 + timedelta(minutes=20)) == 0  # повторно не дублируется

    assert [e.type for e in sink.events] == [EventType.SENSOR_SILENT]
    assert sink.events[0].payload["node_id"] == "node-01"


def test_per_room_silent_min_resolver() -> None:
    """Порог тишины может зависеть от помещения узла (функция-резолвер)."""
    sink = _CollectingSink()
    clock = _Clock(T0)
    rooms = {"cold-01": "cold-01", "room-02": "room-02"}
    # Холодильная камера — строгий порог 5 мин, обычное помещение — 20 мин.
    silent_min_for = {"cold-01": 5, "room-02": 20}.get
    tracker = SilenceTracker(
        sink,
        rooms.get,
        lambda room: silent_min_for(room, 10) if room else 10,
        now_fn=clock.now,
    )
    tracker.record(_reading_in("cold-01", T0))
    tracker.record(_reading_in("room-02", T0))

    # Через 7 минут: холодильная камера уже молчит (порог 5), обычная — нет (порог 20).
    assert tracker.check(T0 + timedelta(minutes=7)) == 1
    assert [e.payload["node_id"] for e in sink.events] == ["cold-01"]


def test_record_resets_silence() -> None:
    """Новое показание сбрасывает эпизод тишины — событие может прийти снова."""
    sink = _CollectingSink()
    clock = _Clock(T0)
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10, now_fn=clock.now)
    tracker.record(_reading("node-01", T0))
    tracker.check(T0 + timedelta(minutes=12))  # первое событие

    clock.t = T0 + timedelta(minutes=15)
    tracker.record(_reading("node-01", clock.t))  # узел снова жив
    assert tracker.check(T0 + timedelta(minutes=30)) == 1  # снова замолчал
    assert len(sink.events) == 2


def test_clock_skew_of_node_does_not_false_flag() -> None:
    """Часы узла отстают на 30 мин — ложного sensor_silent НЕТ (считаем по серверу)."""
    sink = _CollectingSink()
    clock = _Clock(T0)
    tracker = SilenceTracker(sink, {"node-01": "room-01"}.get, silent_min=10, now_fn=clock.now)
    # Узел прислал показание со «своим» временем на 30 минут в прошлом.
    tracker.record(_reading("node-01", T0 - timedelta(minutes=30)))

    # По серверным часам узел активен только что — тишины нет.
    assert tracker.check(T0 + timedelta(minutes=5)) == 0
    assert sink.events == []
