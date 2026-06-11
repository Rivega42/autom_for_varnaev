"""Тесты монитора присутствия (#300): правила из БД, события, эпизоды, TZ."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from scheduler.presence_monitor import PresenceMonitor
from scheduler.tables import events, metadata, presence_rules, rooms
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from monitoring_shared import Event

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(rooms.insert().values(id="room-01", name="Цех приготовления"))
    return engine


def _add_rule(
    engine: Engine,
    start: time = time(8, 0),
    end: time = time(17, 0),
    max_absence_min: int = 30,
    enabled: bool = True,
    room_id: str = "room-01",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            presence_rules.insert().values(
                room_id=room_id,
                window_start=start,
                window_end=end,
                max_absence_min=max_absence_min,
                enabled=enabled,
            )
        )


def _add_presence(engine: Engine, ts: datetime, room_id: str = "room-01") -> None:
    with engine.begin() as conn:
        conn.execute(
            events.insert().values(
                id=uuid4(), ts=ts, type="presence_detected", room_id=room_id, payload={}
            )
        )


def test_missing_emits_once_then_resets_on_presence() -> None:
    """Отсутствие в окне → одно presence_missing; присутствие закрывает эпизод."""
    engine = _engine()
    _add_rule(engine)
    sink = _CollectingSink()
    monitor = PresenceMonitor(sink, UTC)

    assert monitor.check(engine, NOW) == 1  # с 8:00 присутствия не было
    assert monitor.check(engine, NOW + timedelta(minutes=1)) == 0  # тот же эпизод
    event = sink.events[0]
    assert event.type.value == "presence_missing"
    assert event.severity.value == "warning"
    assert event.room_id == "room-01"
    assert "Цех приготовления" in event.message
    assert event.payload["window"] == "08:00–17:00"
    assert event.payload["absent_for_min"] >= 30

    # появилось присутствие → эпизод закрыт, через 31 мин — новое событие
    _add_presence(engine, NOW + timedelta(minutes=2))
    assert monitor.check(engine, NOW + timedelta(minutes=3)) == 0
    assert monitor.check(engine, NOW + timedelta(minutes=33)) == 1


def test_recent_presence_no_event() -> None:
    """Свежее присутствие в окне — события нет."""
    engine = _engine()
    _add_rule(engine)
    _add_presence(engine, NOW - timedelta(minutes=10))
    sink = _CollectingSink()
    assert PresenceMonitor(sink, UTC).check(engine, NOW) == 0
    assert sink.events == []


def test_disabled_rule_and_no_rules_ignored() -> None:
    """Выключенное правило не проверяется; без правил БД не опрашивается."""
    engine = _engine()
    sink = _CollectingSink()
    monitor = PresenceMonitor(sink, UTC)
    assert monitor.check(engine, NOW) == 0
    _add_rule(engine, enabled=False)
    assert monitor.check(engine, NOW) == 0
    assert sink.events == []


def test_window_interpreted_in_presence_tz() -> None:
    """Окно трактуется в PRESENCE_TZ: 12:00 UTC = 15:00 МСК — окно 14–16 МСК активно."""
    engine = _engine()
    _add_rule(engine, start=time(14, 0), end=time(16, 0))
    sink = _CollectingSink()
    moscow = PresenceMonitor(sink, ZoneInfo("Europe/Moscow"))
    assert moscow.check(engine, NOW) == 1  # 15:00 МСК внутри окна, присутствия нет
    # а в UTC 12:00 это окно ещё не началось
    sink_utc = _CollectingSink()
    assert PresenceMonitor(sink_utc, UTC).check(engine, NOW) == 0
