"""Доступ к справочнику узлов датчиков (sensor_nodes) из api-gateway.

Узлы заводятся через интерфейс/REST. Это критично: без узла в справочнике
ingest-sensors отбрасывает показания соответствующего node_id (неизвестный узел).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError

from api_gateway.rooms_repository import room_exists
from api_gateway.schemas import SensorNodeCreate
from api_gateway.tables import sensor_nodes


class NodeAlreadyExistsError(Exception):
    """Узел с таким id уже существует (id — первичный ключ)."""


class RoomNotFoundForNodeError(Exception):
    """Узел ссылается на несуществующее помещение (room_id)."""


def node_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку sensor_nodes в форму ответа API."""
    return {
        "id": row["id"],
        "room_id": row["room_id"],
        "placement": row["placement"],
        "power": row["power"],
        "note": row["note"],
    }


def list_nodes(engine: Engine) -> list[dict[str, Any]]:
    """Список всех узлов датчиков."""
    with engine.connect() as conn:
        return [node_to_api(dict(r)) for r in conn.execute(select(sensor_nodes)).mappings()]


def create_node(engine: Engine, body: SensorNodeCreate) -> dict[str, Any]:
    """Завести узел датчиков; вернуть его в форме API.

    Проверяет, что помещение существует (404), и что id не занят (409). Проверку
    помещения делаем в коде, а не FK — SQLite в тестах не форсит FK по умолчанию.
    """
    if not room_exists(engine, body.room_id):
        raise RoomNotFoundForNodeError(body.room_id)
    values = {
        "id": body.id,
        "room_id": body.room_id,
        "placement": body.placement,
        "power": body.power,
        "note": body.note,
    }
    with engine.begin() as conn:
        clash = conn.execute(select(sensor_nodes.c.id).where(sensor_nodes.c.id == body.id)).first()
        if clash is not None:
            raise NodeAlreadyExistsError(body.id)
        try:
            conn.execute(insert(sensor_nodes).values(**values))
        except IntegrityError as exc:
            # Подстраховка от гонки: дубль id между проверкой и вставкой при
            # одновременных запросах (FastAPI выполняет sync-эндпойнты в пуле).
            raise NodeAlreadyExistsError(body.id) from exc
    return node_to_api(values)
