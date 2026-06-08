"""Тесты чистых функций генератора синтетических показаний."""

import json
import random

from demo_sensors.generator import (
    METRIC_UNITS,
    MetricProfile,
    default_nodes,
    reading_payload,
    reading_topic,
    synth_value,
)

from monitoring_shared import Metric


def test_topic_format() -> None:
    """Топик собирается как <prefix>/<node>/<metric>."""
    assert reading_topic("monitoring", "node-01", Metric.AIR_TEMP) == "monitoring/node-01/air_temp"


def test_payload_has_value_and_unit() -> None:
    """payload — валидный JSON с обязательными полями value и unit."""
    data = json.loads(reading_payload(Metric.HUMIDITY, 45.0))
    assert data == {"value": 45.0, "unit": "%"}


def test_synth_value_within_band() -> None:
    """Без всплеска значение держится в пределах base ± jitter."""
    profile = MetricProfile(Metric.AIR_TEMP, base=22.0, jitter=2.0)
    rng = random.Random(0)
    for step in range(100):
        value = synth_value(profile, step=step, rng=rng, spike=False)
        assert 20.0 <= value <= 24.0


def test_spike_returns_anomaly() -> None:
    """Со всплеском и заданным spike возвращается аномальное значение."""
    profile = MetricProfile(Metric.AIR_TEMP, base=4.0, jitter=1.0, spike=12.0)
    assert synth_value(profile, step=3, rng=random.Random(0), spike=True) == 12.0


def test_spike_ignored_when_no_spike_value() -> None:
    """Если у метрики нет spike, флаг всплеска не выводит из нормального диапазона."""
    profile = MetricProfile(Metric.HUMIDITY, base=60.0, jitter=4.0)
    value = synth_value(profile, step=3, rng=random.Random(0), spike=True)
    assert 56.0 <= value <= 64.0


def test_default_nodes_units_consistent() -> None:
    """Единицы во всех профилях демо-узлов соответствуют таблице METRIC_UNITS."""
    for node in default_nodes():
        for profile in node.metrics:
            data = json.loads(reading_payload(profile.metric, 1.0))
            assert data["unit"] == METRIC_UNITS[profile.metric]


def test_default_nodes_have_breaching_spikes() -> None:
    """Демо-топология содержит всплески, пробивающие демо-пороги (>70% и >8 °C)."""
    spikes = {
        (node.node_id, profile.metric): profile.spike
        for node in default_nodes()
        for profile in node.metrics
        if profile.spike is not None
    }
    assert spikes[("node-01", Metric.HUMIDITY)] > 70.0
    assert spikes[("node-02", Metric.AIR_TEMP)] > 8.0
