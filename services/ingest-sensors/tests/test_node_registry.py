"""NodeRegistry: справочник узлов node_id → room_id с горячим перечитом (#355)."""

from ingest_sensors.node_registry import NodeRegistry, load_node_rooms
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE sensor_nodes (id TEXT, room_id TEXT)"))
        conn.execute(
            text("INSERT INTO sensor_nodes VALUES ('node-01', 'room-01'), ('node-02', 'room-02')")
        )
    return eng


def _add_node(eng: Engine, node_id: str, room_id: str) -> None:
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO sensor_nodes VALUES (:n, :r)"), {"n": node_id, "r": room_id})


def test_resolve_known_and_unknown() -> None:
    reg = NodeRegistry(_engine())
    assert reg.resolve("node-01") == "room-01"
    assert reg.resolve("node-02") == "room-02"
    assert reg.resolve("node-99") is None
    assert len(reg) == 2


def test_refresh_picks_up_new_node_without_restart() -> None:
    """Узел, добавленный ПОСЛЕ старта, подхватывается после refresh() — без рестарта (#355)."""
    eng = _engine()
    reg = NodeRegistry(eng)
    assert reg.resolve("node-03") is None  # ещё нет в справочнике
    _add_node(eng, "node-03", "room-03")
    assert reg.resolve("node-03") is None  # до refresh — всё ещё неизвестен (кэш)
    reg.refresh()
    assert reg.resolve("node-03") == "room-03"  # после refresh — принят
    assert len(reg) == 3


def test_load_node_rooms() -> None:
    assert load_node_rooms(_engine()) == {"node-01": "room-01", "node-02": "room-02"}
