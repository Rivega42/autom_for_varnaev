"""Тесты диспетчера уведомлений (#264): правило, рассылка, гашение сбоев."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from log_service.app import create_app
from log_service.notifications import Notifier, format_event

from monitoring_shared import Event, EventSource, EventType, Severity


def _event(
    severity: Severity = Severity.WARNING, type_: EventType = EventType.THRESHOLD_EXCEEDED
) -> Event:
    return Event(
        id=uuid4(),
        ts=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
        source=EventSource.SENSORS,
        type=type_,
        room_id="cold-01",
        severity=severity,
        message="В холодильной камере температура выше нормы",
    )


class _RecordingChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, subject: str, body: str, event: Event) -> None:
        self.sent.append((subject, body))


class _BrokenChannel:
    def send(self, subject: str, body: str, event: Event) -> None:
        raise RuntimeError("канал недоступен")


def test_rule_filters_below_min_severity() -> None:
    """Событие ниже порога важности не рассылается."""
    ch = _RecordingChannel()
    n = Notifier([ch], min_severity=Severity.WARNING)
    assert n.notify(_event(Severity.INFO)) == 0
    assert ch.sent == []


def test_dispatches_at_or_above_severity() -> None:
    """Событие на пороге/выше уходит во все каналы."""
    a, b = _RecordingChannel(), _RecordingChannel()
    n = Notifier([a, b], min_severity=Severity.WARNING)
    assert n.notify(_event(Severity.CRITICAL)) == 2
    assert len(a.sent) == 1 and len(b.sent) == 1


def test_type_allowlist() -> None:
    """Фильтр по типу события."""
    ch = _RecordingChannel()
    n = Notifier([ch], min_severity=Severity.INFO, types=frozenset({"sensor_silent"}))
    assert n.notify(_event(type_=EventType.THRESHOLD_EXCEEDED)) == 0
    assert n.notify(_event(type_=EventType.SENSOR_SILENT)) == 1


def test_broken_channel_swallowed_others_still_sent() -> None:
    """Сбой одного канала не мешает остальным и не пробрасывает исключение."""
    ok_ch = _RecordingChannel()
    n = Notifier([_BrokenChannel(), ok_ch], min_severity=Severity.WARNING)
    assert n.notify(_event(Severity.WARNING)) == 1
    assert len(ok_ch.sent) == 1


def test_format_event_ru() -> None:
    """Заголовок и тело содержат сообщение, помещение и важность."""
    subject, body = format_event(_event(Severity.CRITICAL))
    assert "critical" in subject and "cold-01" in subject
    assert "температура выше нормы" in body


def test_no_channels_is_noop() -> None:
    """Без каналов уведомления отключены."""
    assert Notifier([], min_severity=Severity.INFO).notify(_event(Severity.CRITICAL)) == 0


def test_endpoint_dispatches_after_insert() -> None:
    """POST /events рассылает уведомление после записи (через инъецированный notifier)."""
    ch = _RecordingChannel()
    notifier = Notifier([ch], min_severity=Severity.WARNING)
    from log_service.tables import metadata
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    client = TestClient(create_app(engine=engine, notifier=notifier))

    body = _event(Severity.CRITICAL).model_dump(mode="json")
    resp = client.post("/events", json=body)
    assert resp.status_code == 200
    assert len(ch.sent) == 1
