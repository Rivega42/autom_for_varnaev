"""Справочник узлов node_id → room_id с горячим перечитом из БД (#355).

Узел, заведённый на работающем стеке (GUI/REST `POST /sensor-nodes`), должен
подхватываться **без перезапуска** воркера. Поэтому справочник держится в
NodeRegistry и перечитывается на каждом тике (см. main.on_tick) — ровно как
пороги (ThresholdMonitor). Иначе новый узел считается «неизвестным» и его
показания отбрасываются до ручного рестарта.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)


def load_node_rooms(engine: Engine) -> dict[str, str]:
    """Загрузить соответствие node_id → room_id из справочника sensor_nodes."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, room_id FROM sensor_nodes")).mappings().all()
    return {row["id"]: row["room_id"] for row in rows}


class NodeRegistry:
    """node_id → room_id из sensor_nodes с горячим перечитом (#355).

    `resolve(node_id)` → room_id или None (узел не в справочнике — показание
    отбрасывается). `refresh()` перечитывает справочник из БД, чтобы новые узлы
    подхватывались без рестарта воркера.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._rooms: dict[str, str] = load_node_rooms(engine)

    def refresh(self) -> None:
        """Перечитать справочник sensor_nodes из БД (вызывается на тике)."""
        self._rooms = load_node_rooms(self._engine)

    def resolve(self, node_id: str) -> str | None:
        """room_id узла или None, если узел не в справочнике."""
        return self._rooms.get(node_id)

    def __len__(self) -> int:
        return len(self._rooms)
