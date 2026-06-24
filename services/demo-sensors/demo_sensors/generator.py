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
    Metric.UV_INDEX: "index",
    Metric.UV_C: "mW/cm2",
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
    """Демо-топология объекта: 6 помещений, 6 узлов (совпадают с db/seeds/demo.yaml).

    Всплески подобраны под демо-пороги (db/seeds/demo.yaml), чтобы в журнале
    периодически появлялись РАЗНЫЕ события по разным помещениям:
    - влажность node-kitchen → 82% и node-wash → 80% (> 70%);
    - темп. воздуха node-fridge → 10 °C (> 8 °C в холодильной камере);
    - темп. воздуха node-freezer → -12 °C (> -15 °C в морозильной — разморозка);
    - ИК-поверхность node-kitchen → 38 °C (> 35 °C — горячая поверхность).
    """
    return [
        # Кухня (room-01): полный узел — воздух, ИК-поверхность, УФ-лампа.
        NodeProfile(
            "node-kitchen",
            [
                MetricProfile(Metric.AIR_TEMP, base=22.0, jitter=1.5),
                MetricProfile(Metric.HUMIDITY, base=46.0, jitter=6.0, spike=82.0),
                MetricProfile(Metric.SURFACE_IR, base=22.0, jitter=3.0, spike=38.0),
                MetricProfile(Metric.UV_INDEX, base=1.0, jitter=0.6),
                MetricProfile(Metric.UV_C, base=2.2, jitter=0.5),
            ],
        ),
        # Холодильная камера +2..+8 (room-02): зонд воздуха + влажность.
        NodeProfile(
            "node-fridge",
            [
                MetricProfile(Metric.AIR_TEMP, base=4.0, jitter=1.0, spike=10.0),
                MetricProfile(Metric.HUMIDITY, base=60.0, jitter=5.0),
            ],
        ),
        # Морозильная камера -18..-25 (room-03): зонд воздуха.
        NodeProfile(
            "node-freezer",
            [
                MetricProfile(Metric.AIR_TEMP, base=-20.0, jitter=1.5, spike=-12.0),
                MetricProfile(Metric.HUMIDITY, base=55.0, jitter=5.0),
            ],
        ),
        # Моечная (room-04): влажная зона — влажность периодически выше нормы.
        NodeProfile(
            "node-wash",
            [
                MetricProfile(Metric.AIR_TEMP, base=24.0, jitter=1.5),
                MetricProfile(Metric.HUMIDITY, base=66.0, jitter=8.0, spike=80.0),
            ],
        ),
        # Зона фасовки (room-05): воздух.
        NodeProfile(
            "node-packing",
            [
                MetricProfile(Metric.AIR_TEMP, base=18.0, jitter=1.2),
                MetricProfile(Metric.HUMIDITY, base=50.0, jitter=5.0),
            ],
        ),
        # Склад сухих продуктов (room-06): воздух.
        NodeProfile(
            "node-storage",
            [
                MetricProfile(Metric.AIR_TEMP, base=20.0, jitter=1.5),
                MetricProfile(Metric.HUMIDITY, base=48.0, jitter=5.0),
            ],
        ),
    ]
