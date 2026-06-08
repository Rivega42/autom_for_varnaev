"""Проверка разбора и валидации конфига сидов (без обращения к БД)."""

from pathlib import Path

from monitoring_shared import Metric, Severity, ThresholdOp
from seed import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_example_config() -> None:
    """Пример-конфиг разбирается и валидируется моделями."""
    rooms, nodes, cameras, thresholds = load_config(REPO_ROOT / "db/seeds/object.example.yaml")
    assert {r.id for r in rooms} == {"room-01", "room-02"}
    # холодильная камера помечена is_cold
    assert any(r.is_cold for r in rooms)
    assert {n.id for n in nodes} == {"node-01", "node-02"}
    assert cameras[0].room_id == "room-01"
    # пороги разобраны и провалидированы (room=None — глобальный)
    assert any(t.room is None and t.metric is Metric.HUMIDITY for t in thresholds)
    cold = next(t for t in thresholds if t.room == "room-02")
    assert cold.metric is Metric.AIR_TEMP
    assert cold.op is ThresholdOp.GT
    assert cold.severity is Severity.CRITICAL
    assert cold.silent_min == 10


def test_load_demo_config() -> None:
    """Демо-конфиг разбирается; пороги подобраны под всплески генератора."""
    rooms, nodes, cameras, thresholds = load_config(REPO_ROOT / "db/seeds/demo.yaml")
    assert {r.id for r in rooms} == {"room-01", "room-02"}
    assert {n.id for n in nodes} == {"node-01", "node-02"}
    assert cameras == []  # видео в демо нет
    spikes = {(t.room, t.metric): t.value for t in thresholds}
    assert spikes[(None, Metric.HUMIDITY)] == 70.0
    assert spikes[("room-02", Metric.AIR_TEMP)] == 8.0


def test_empty_config_yields_empty_lists(tmp_path: Path) -> None:
    """Отсутствие секций (или пустой файл) даёт пустые списки, в т.ч. thresholds."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty) == ([], [], [], [])
