"""Проверка сверки порогов и отслеживания состояния."""

from ingest_sensors.thresholds import (
    ThresholdMonitor,
    Transition,
    applicable_thresholds,
    compare,
    load_thresholds,
)
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from monitoring_shared import Metric, Severity, Threshold, ThresholdOp


def _threshold(**kw: object) -> Threshold:
    base: dict[str, object] = {
        "id": 1,
        "room_id": None,
        "metric": Metric.AIR_TEMP,
        "op": ThresholdOp.GT,
        "value": 8.0,
        "severity": Severity.WARNING,
        "silent_min": None,
        "enabled": True,
    }
    base.update(kw)
    return Threshold(**base)  # type: ignore[arg-type]


def test_compare_operators() -> None:
    assert compare(ThresholdOp.GT, 8.7, 8.0) is True
    assert compare(ThresholdOp.LT, 8.7, 8.0) is False
    assert compare(ThresholdOp.LE, 8.0, 8.0) is True


def test_applicable_filters_by_metric_room_enabled() -> None:
    thresholds = [
        _threshold(id=1, room_id=None, metric=Metric.AIR_TEMP),
        _threshold(id=2, room_id="room-02", metric=Metric.AIR_TEMP),
        _threshold(id=3, metric=Metric.HUMIDITY),
        _threshold(id=4, enabled=False),
    ]
    got = applicable_thresholds(thresholds, "room-01", Metric.AIR_TEMP)
    # глобальный (id=1) подходит; id=2 — другое помещение; id=3 — др. метрика; id=4 — выключен
    assert [t.id for t in got] == [1]


def test_monitor_transitions() -> None:
    monitor = ThresholdMonitor([_threshold(value=8.0, op=ThresholdOp.GT)])
    # норма → превышение
    assert monitor.evaluate("room-01", Metric.AIR_TEMP, 9.0)[0] is Transition.BREACHED
    # остаётся выше — без перехода
    assert monitor.evaluate("room-01", Metric.AIR_TEMP, 9.5)[0] is Transition.NONE
    # вернулось в норму
    assert monitor.evaluate("room-01", Metric.AIR_TEMP, 7.0)[0] is Transition.RECOVERED
    # снова норма — без перехода
    assert monitor.evaluate("room-01", Metric.AIR_TEMP, 6.0)[0] is Transition.NONE


def test_load_thresholds_from_db() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE thresholds (id INTEGER, room_id TEXT, metric TEXT, op TEXT, "
                "value REAL, severity TEXT, silent_min INTEGER, enabled BOOLEAN)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO thresholds VALUES "
                "(1, NULL, 'air_temp', '>', 8.0, 'warning', NULL, 1), "
                "(2, NULL, 'humidity', '>', 80.0, 'warning', NULL, 0)"
            )
        )
    loaded = load_thresholds(engine)
    # загружается только включённый порог (id=1)
    assert [t.id for t in loaded] == [1]
    assert loaded[0].metric is Metric.AIR_TEMP
    assert loaded[0].op is ThresholdOp.GT
