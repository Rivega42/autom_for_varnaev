"""Тесты хранилища и монитора контроля уборки (#265, часть 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from scheduler.cleaning_monitor import CleaningMonitor
from scheduler.cleaning_store import load_cleaning_rules, load_last_cleanings
from scheduler.tables import cleaning_rules, events, metadata
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from monitoring_shared import Event

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine


def _add_rule(engine: Engine, room: str = "room-01", enabled: bool = True) -> None:
    with engine.begin() as conn:
        conn.execute(
            cleaning_rules.insert().values(
                room_id=room,
                zone_type="table",
                interval_hours=4.0,
                min_coverage_pct=60,
                zone_name="стол у плиты",
                enabled=enabled,
            )
        )


def _add_coverage(engine: Engine, room: str, zone: str, pct: int, ts: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            events.insert().values(
                id=uuid4(),
                ts=ts,
                type="coverage_report",
                room_id=room,
                payload={"zone": zone, "zone_id": 1, "coverage_pct": pct},
            )
        )


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def test_load_rules_only_enabled() -> None:
    """Загружаются только включённые правила."""
    engine = _engine()
    _add_rule(engine, "room-01", enabled=True)
    _add_rule(engine, "room-02", enabled=False)
    rules = load_cleaning_rules(engine)
    assert [r.room_id for r in rules] == ["room-01"]
    assert rules[0].zone_name == "стол у плиты"


def test_load_last_cleanings_latest_wins() -> None:
    """Из нескольких coverage_report берётся последний по времени."""
    engine = _engine()
    _add_rule(engine)
    _add_coverage(engine, "room-01", "table", 50, NOW - timedelta(hours=3))
    _add_coverage(engine, "room-01", "table", 90, NOW - timedelta(hours=1))
    last = load_last_cleanings(engine, load_cleaning_rules(engine), NOW)
    assert last[("room-01", "table")].coverage_pct == 90


def test_monitor_emits_overdue_once(caplog: pytest.LogCaptureFixture) -> None:
    """Монитор эмитит cleaning_overdue один раз на эпизод; норма — сбрасывает."""
    engine = _engine()
    _add_rule(engine)
    sink = _CollectingSink()
    monitor = CleaningMonitor(sink)

    # уборки не было → просрочка, событие одно
    assert monitor.check(engine, NOW) == 1
    assert monitor.check(engine, NOW + timedelta(minutes=1)) == 0
    ev = sink.events[0]
    assert ev.type.value == "cleaning_overdue"
    assert ev.severity.value == "warning"
    assert "стол у плиты" in ev.message
    assert ev.payload["zone"] == "table"

    # зону убрали с нормальным покрытием → эпизод закрыт, событий нет
    _add_coverage(engine, "room-01", "table", 95, NOW + timedelta(minutes=2))
    assert monitor.check(engine, NOW + timedelta(minutes=3)) == 0

    # снова просрочили → новый эпизод, новое событие
    assert monitor.check(engine, NOW + timedelta(hours=10)) == 1
    assert len(sink.events) == 2


def test_monitor_low_coverage_triggers() -> None:
    """Свежая уборка с покрытием ниже порога — тоже просрочка."""
    engine = _engine()
    _add_rule(engine)  # min 60%
    _add_coverage(engine, "room-01", "table", 30, NOW - timedelta(minutes=30))
    sink = _CollectingSink()
    assert CleaningMonitor(sink).check(engine, NOW) == 1
    assert "ниже нормы" in sink.events[0].message


def test_monitor_no_rules_noop() -> None:
    """Без правил монитор ничего не делает."""
    engine = _engine()
    sink = _CollectingSink()
    assert CleaningMonitor(sink).check(engine, NOW) == 0
    assert sink.events == []
