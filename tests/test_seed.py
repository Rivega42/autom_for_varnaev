"""Проверка разбора и валидации конфига сидов (без обращения к БД)."""

from pathlib import Path

from seed import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_example_config() -> None:
    """Пример-конфиг разбирается и валидируется моделями."""
    rooms, nodes, cameras = load_config(REPO_ROOT / "db/seeds/object.example.yaml")
    assert {r.id for r in rooms} == {"room-01", "room-02"}
    # холодильная камера помечена is_cold
    assert any(r.is_cold for r in rooms)
    assert {n.id for n in nodes} == {"node-01", "node-02"}
    assert cameras[0].room_id == "room-01"
