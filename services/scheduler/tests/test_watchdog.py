"""Тесты watchdog живости сервисов (#284): свежесть heartbeat, эпизоды, UPSERT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scheduler.heartbeat import load_heartbeats, write_heartbeat
from scheduler.tables import metadata, service_heartbeats
from scheduler.watchdog import ServiceWatchdog, evaluate_silent
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool

from monitoring_shared import Event

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


# ── Чистое ядро evaluate_silent ──


def test_evaluate_flags_stale_once_and_recovers() -> None:
    """Просрочка → один раз в newly_silent; свежий heartbeat снимает флаг."""
    hb = {"ingest-sensors": NOW - timedelta(minutes=10)}
    silent, _recovered, flagged = evaluate_silent(hb, NOW, silent_min=5, flagged=set())
    assert [s.service for s in silent] == ["ingest-sensors"]
    assert silent[0].silent_for_min == 10
    assert flagged == {"ingest-sensors"}

    # тот же эпизод — повтора нет
    silent2, rec2, flagged2 = evaluate_silent(hb, NOW, 5, flagged)
    assert silent2 == [] and rec2 == [] and flagged2 == {"ingest-sensors"}

    # сервис вернулся (свежий ts) → recovered, флаг снят
    hb_fresh = {"ingest-sensors": NOW - timedelta(minutes=1)}
    silent3, rec3, flagged3 = evaluate_silent(hb_fresh, NOW, 5, flagged2)
    assert silent3 == [] and rec3 == ["ingest-sensors"] and flagged3 == set()


def test_evaluate_fresh_service_no_events() -> None:
    """Свежий heartbeat в пределах порога — событий нет."""
    hb = {"scheduler": NOW - timedelta(minutes=1)}
    silent, recovered, flagged = evaluate_silent(hb, NOW, silent_min=5, flagged=set())
    assert silent == [] and recovered == [] and flagged == set()


def test_evaluate_handles_naive_ts() -> None:
    """Naive-время (SQLite) трактуется как UTC — без ошибки сравнения tz."""
    hb = {"video-analytics": (NOW - timedelta(minutes=30)).replace(tzinfo=None)}
    silent, _, _ = evaluate_silent(hb, NOW, silent_min=5, flagged=set())
    assert [s.service for s in silent] == ["video-analytics"]


# ── UPSERT и чтение heartbeat ──


def test_write_heartbeat_upserts() -> None:
    """Повторная запись обновляет ts той же строки (UPSERT по service)."""
    engine = _engine()
    write_heartbeat(engine, "scheduler", NOW)
    write_heartbeat(engine, "scheduler", NOW + timedelta(minutes=2))
    with engine.connect() as conn:
        rows = conn.execute(select(service_heartbeats)).all()
    assert len(rows) == 1  # одна строка, а не две
    assert load_heartbeats(engine)["scheduler"].replace(tzinfo=UTC) == NOW + timedelta(minutes=2)


# ── Монитор ServiceWatchdog ──


def test_watchdog_emits_silent_then_restored() -> None:
    """Замолчавший сервис → service_silent один раз; возврат → service_restored."""
    engine = _engine()
    write_heartbeat(engine, "ingest-sensors", NOW - timedelta(minutes=20))
    sink = _CollectingSink()
    wd = ServiceWatchdog(sink, silent_min=5)

    assert wd.check(engine, NOW) == 1
    assert wd.check(engine, NOW) == 0  # тот же эпизод
    ev = sink.events[0]
    assert ev.type.value == "service_silent"
    assert ev.severity.value == "warning"
    assert "ingest-sensors" in ev.message
    assert ev.payload["service"] == "ingest-sensors"

    # сервис вернулся → service_restored
    write_heartbeat(engine, "ingest-sensors", NOW)
    assert wd.check(engine, NOW) == 1
    assert sink.events[1].type.value == "service_restored"
    assert sink.events[1].severity.value == "info"


def test_watchdog_no_heartbeats_noop() -> None:
    """Нет heartbeat'ов — нечего проверять."""
    engine = _engine()
    sink = _CollectingSink()
    assert ServiceWatchdog(sink, silent_min=5).check(engine, NOW) == 0
    assert sink.events == []
