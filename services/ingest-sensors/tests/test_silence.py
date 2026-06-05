"""Проверка контроля «тишины» узлов и события sensor_silent."""

from datetime import UTC, datetime, timedelta

from ingest_sensors.events import build_sensor_silent
from ingest_sensors.silence import SilenceMonitor

from monitoring_shared import EventType, Severity

_T0 = datetime(2026, 6, 5, 10, 0, tzinfo=UTC)


def test_silence_reported_once_then_reset() -> None:
    """Узел, молчащий дольше порога, сообщается однократно; запись сбрасывает."""
    monitor = SilenceMonitor()
    monitor.record("node-01", _T0)

    # Через 5 минут при пороге 10 — ещё не тишина
    assert monitor.silent_nodes(_T0 + timedelta(minutes=5), silent_min=10) == []
    # Через 12 минут — тишина, отчёт один раз
    silent = monitor.silent_nodes(_T0 + timedelta(minutes=12), silent_min=10)
    assert silent == [("node-01", 12)]
    # Повторный вызов — без дублей
    assert monitor.silent_nodes(_T0 + timedelta(minutes=13), silent_min=10) == []
    # Новое показание — признак тишины сброшен
    monitor.record("node-01", _T0 + timedelta(minutes=14))
    assert monitor.silent_nodes(_T0 + timedelta(minutes=15), silent_min=10) == []


def test_build_sensor_silent_message() -> None:
    """Событие sensor_silent несёт русский message с контекстом помещения."""
    event = build_sensor_silent("node-03", "room-02", 12, _T0, lambda _r: "холодильной камере")
    assert event.type is EventType.SENSOR_SILENT
    assert event.severity is Severity.WARNING
    assert event.message == "Датчик в холодильной камере молчит 12 мин"
    assert event.payload["node_id"] == "node-03"
