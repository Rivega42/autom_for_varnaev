"""Проверка демо-сида: разбор демо-конфига и согласованность демо-порогов."""

from pathlib import Path

from demo_seed import _DEMO_THRESHOLDS
from seed import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_demo_config() -> None:
    """db/seeds/demo.yaml разбирается и валидируется моделями."""
    rooms, nodes, cameras = load_config(REPO_ROOT / "db/seeds/demo.yaml")
    assert {r.id for r in rooms} == {"room-01", "room-02"}
    assert any(r.is_cold for r in rooms)  # холодильная камера помечена
    assert {n.id for n in nodes} == {"node-01", "node-02"}
    assert cameras == []  # видео в демо нет


def test_demo_thresholds_reference_demo_rooms() -> None:
    """Демо-пороги ссылаются на существующие помещения демо-конфига."""
    rooms, _, _ = load_config(REPO_ROOT / "db/seeds/demo.yaml")
    room_ids = {r.id for r in rooms}
    for room, _metric, op, _value, severity in _DEMO_THRESHOLDS:
        assert room is None or room in room_ids
        assert op in {">", "<", ">=", "<="}
        assert severity in {"info", "warning", "critical"}
