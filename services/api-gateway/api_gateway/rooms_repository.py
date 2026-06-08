"""Доступ к справочнику помещений (rooms) из api-gateway.

Помещения заводятся через интерфейс/REST (без SQL и сидинга): они нужны как
первичный ключ для узлов датчиков, камер, показаний и событий.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError

from api_gateway.schemas import RoomCreate
from api_gateway.tables import rooms


class RoomAlreadyExistsError(Exception):
    """Помещение с таким id уже существует (id — первичный ключ)."""


def room_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку rooms в форму ответа API."""
    return {
        "id": row["id"],
        "name": row["name"],
        "is_cold": bool(row["is_cold"]),
    }


def list_rooms(engine: Engine) -> list[dict[str, Any]]:
    """Список всех помещений."""
    with engine.connect() as conn:
        return [room_to_api(dict(r)) for r in conn.execute(select(rooms)).mappings()]


def room_exists(engine: Engine, room_id: str) -> bool:
    """Есть ли помещение с таким id."""
    with engine.connect() as conn:
        return conn.execute(select(rooms.c.id).where(rooms.c.id == room_id)).first() is not None


def create_room(engine: Engine, body: RoomCreate) -> dict[str, Any]:
    """Завести помещение; вернуть его в форме API (409 при занятом id)."""
    values = {"id": body.id, "name": body.name, "is_cold": body.is_cold}
    with engine.begin() as conn:
        clash = conn.execute(select(rooms.c.id).where(rooms.c.id == body.id)).first()
        if clash is not None:
            raise RoomAlreadyExistsError(body.id)
        try:
            conn.execute(insert(rooms).values(**values))
        except IntegrityError as exc:
            # Подстраховка от гонки: дубль id между проверкой и вставкой при
            # одновременных запросах (FastAPI выполняет sync-эндпойнты в пуле).
            raise RoomAlreadyExistsError(body.id) from exc
    return room_to_api(values)
