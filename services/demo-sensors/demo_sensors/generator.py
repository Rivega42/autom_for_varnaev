"""Чистые функции генерации синтетических показаний датчиков.

Без сети — чтобы поведение можно было покрыть тестами. Значения строятся как
плавное «блуждание» вокруг базового уровня (синус + небольшой шум), что внешне
похоже на реальный ряд. Периодический «всплеск» выдаёт аномальное значение,
чтобы в демо срабатывали пороги и в журнал попадали события. Сетевой цикл
публикации в MQTT — в main.py.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass

from monitoring_shared import Metric

# Единицы измерения по метрике — ровно то, что ожидает ingest-sensors в payload.
METRIC_UNITS: dict[Metric, str] = {
    Metric.AIR_TEMP: "C",
    Metric.HUMIDITY: "%",
    Metric.SURFACE_IR: "C",
}


@dataclass
class MetricProfile:
    """Профиль метрики узла: базовый уровень, амплитуда и значение всплеска."""

    metric: Metric
    base: float
    jitter: float
    # Значение аномального всплеска (пробивает порог) или None, если всплесков нет.
    spike: float | None = None


@dataclass
class NodeProfile:
    """Узел демо-стенда: идентификатор и его метрики."""

    node_id: str
    metrics: list[MetricProfile]


def synth_value(profile: MetricProfile, *, step: int, rng: random.Random, spike: bool) -> float:
    """Сгенерировать значение метрики на шаге `step`.

    При `spike=True` и заданном `profile.spike` возвращается аномальное значение
    (для пробоя порога). Иначе — плавное блуждание в пределах base ± jitter.
    """
    if spike and profile.spike is not None:
        return profile.spike
    wave = math.sin(step / 6.0) * (profile.jitter / 2.0)
    noise = rng.uniform(-profile.jitter / 2.0, profile.jitter / 2.0)
    return round(profile.base + wave + noise, 2)


def reading_topic(prefix: str, node_id: str, metric: Metric) -> str:
    """Топик показания: <prefix>/<node_id>/<metric> (как подписан ingest-sensors)."""
    return f"{prefix}/{node_id}/{metric.value}"


def reading_payload(metric: Metric, value: float) -> bytes:
    """JSON-payload показания: {"value": ..., "unit": ...} в UTF-8."""
    return json.dumps({"value": value, "unit": METRIC_UNITS[metric]}).encode("utf-8")


def default_nodes() -> list[NodeProfile]:
    """Демо-топология: кухня (room-01/node-01) и холодильная камера (room-02/node-02).

    Узлы и помещения совпадают с db/seeds/demo.yaml. Всплески подобраны под
    демо-пороги (см. scripts/demo_seed.py): влажность node-01 → 82% (> 70%),
    темп. воздуха node-02 → 12 °C (> 8 °C в холодильной камере).
    """
    return [
        NodeProfile(
            "node-01",
            [
                MetricProfile(Metric.AIR_TEMP, base=22.0, jitter=1.5),
                MetricProfile(Metric.HUMIDITY, base=45.0, jitter=6.0, spike=82.0),
                MetricProfile(Metric.SURFACE_IR, base=20.0, jitter=1.0),
            ],
        ),
        NodeProfile(
            "node-02",
            [
                MetricProfile(Metric.AIR_TEMP, base=4.0, jitter=1.0, spike=12.0),
                MetricProfile(Metric.HUMIDITY, base=60.0, jitter=5.0),
            ],
        ),
    ]
