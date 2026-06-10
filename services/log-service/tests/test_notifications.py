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


def test_build_notifier_bad_severity_falls_back(monkeypatch) -> None:
    """Некорректный NOTIFY_MIN_SEVERITY не роняет старт — fallback на warning."""
    import log_service.notifications as notif

    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "КРИТ")
    n = notif.build_notifier_from_env()  # не должно бросить
    assert n.notify(_event(Severity.INFO)) == 0  # каналов нет — noop, но не упало


def test_build_notifier_bad_smtp_port_falls_back(monkeypatch) -> None:
    """Нечисловой SMTP_PORT не роняет старт."""
    import log_service.notifications as notif

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "abc")
    monkeypatch.setenv("NOTIFY_EMAIL_FROM", "a@example.com")
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "b@example.com")
    notif.build_notifier_from_env()  # не должно бросить ValueError


def test_telegram_truncates_long_text(monkeypatch) -> None:
    """Длинный текст усекается до лимита Telegram (нет HTTP 400)."""
    from log_service.notifications import TelegramChannel

    captured = {}

    class _FakeResp:
        def raise_for_status(self) -> None:
            pass

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            pass

        def post(self, url, json):
            captured["len"] = len(json["text"])
            return _FakeResp()

    monkeypatch.setattr("log_service.notifications.httpx.Client", _FakeClient)
    ch = TelegramChannel("token", "chat")
    ev = _event(Severity.CRITICAL)
    ev = ev.model_copy(update={"message": "x" * 9000})
    ch.send(*format_event(ev)[:2], ev)
    assert captured["len"] <= 4096


def _sqlite_app(notifier: Notifier | None = None):
    from log_service.tables import metadata
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine, TestClient(create_app(engine=engine, notifier=notifier or Notifier([])))


def test_ack_endpoint_idempotent_and_404() -> None:
    """POST /events/{id}/ack подтверждает (идемпотентно); чужой id → 404."""
    _engine, client = _sqlite_app()
    ev = _event(Severity.CRITICAL)
    assert client.post("/events", json=ev.model_dump(mode="json")).status_code == 200

    first = client.post(f"/events/{ev.id}/ack")
    assert first.status_code == 200 and first.json()["data"]["acknowledged"] is True
    second = client.post(f"/events/{ev.id}/ack")  # повтор — тоже 200
    assert second.status_code == 200

    listed = client.get("/events").json()["data"]["items"][0]
    assert listed["acknowledged_at"] is not None

    from uuid import uuid4 as _u

    assert client.post(f"/events/{_u()}/ack").status_code == 404


def test_escalation_repeats_until_ack() -> None:
    """Неподтверждённое критичное событие повторяется; после ack — тишина."""
    from datetime import timedelta

    from log_service.escalation import EscalationSettings, Escalator
    from log_service.repository import ack_event

    ch = _RecordingChannel()
    notifier = Notifier([ch], min_severity=Severity.WARNING)
    engine, client = _sqlite_app(notifier)
    ev = _event(Severity.CRITICAL)
    client.post("/events", json=ev.model_dump(mode="json"))
    assert len(ch.sent) == 1  # первичное уведомление

    esc = Escalator(notifier, EscalationSettings(after_min=5, repeat_min=10, max_repeats=2))
    t0 = ev.ts

    # рано (3 мин) — повтора нет
    assert esc.check_once(engine, t0 + timedelta(minutes=3)) == 0
    # 6 мин — первый повтор с пометкой
    assert esc.check_once(engine, t0 + timedelta(minutes=6)) == 1
    assert "ПОВТОР 1" in ch.sent[-1][0] + ch.sent[-1][1]
    # сразу ещё раз — пауза repeat_min не прошла
    assert esc.check_once(engine, t0 + timedelta(minutes=7)) == 0
    # после паузы — второй повтор
    assert esc.check_once(engine, t0 + timedelta(minutes=17)) == 1
    # лимит повторов исчерпан
    assert esc.check_once(engine, t0 + timedelta(minutes=40)) == 0

    # новый цикл: другое событие, ack останавливает эскалацию
    ev2 = _event(Severity.CRITICAL)
    client.post("/events", json=ev2.model_dump(mode="json"))
    ack_event(engine, ev2.id, t0 + timedelta(minutes=1))
    assert esc.check_once(engine, t0 + timedelta(minutes=20)) == 0


def test_escalation_disabled_by_default() -> None:
    """after_min=0 — эскалация выключена."""
    from log_service.escalation import EscalationSettings, Escalator

    ch = _RecordingChannel()
    engine, client = _sqlite_app(Notifier([ch], min_severity=Severity.WARNING))
    client.post("/events", json=_event(Severity.CRITICAL).model_dump(mode="json"))
    esc = Escalator(Notifier([ch]), EscalationSettings())  # after_min=0
    assert esc.check_once(engine, datetime(2026, 6, 10, 12, 0, tzinfo=UTC)) == 0
