"""Доступ к ROI-зонам камер (camera_zones) из api-gateway.

Интерфейс настройки зон покрытия: список/создание/изменение/удаление полигонов
ROI для камеры. По этим зонам видеоаналитика считает % покрытия (coverage_report).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, delete, select, update

from api_gateway.schemas import CameraZoneCreate, CameraZoneUpdate
from api_gateway.tables import camera_zones


def zone_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку camera_zones в форму ответа API."""
    return {
        "id": row["id"],
        "camera_id": str(row["camera_id"]),
        "zone_type": row["zone_type"],
        "polygon": row["polygon"],
        "note": row.get("note"),
    }


def list_zones(engine: Engine, camera_id: UUID) -> list[dict[str, Any]]:
    """ROI-зоны камеры."""
    stmt = select(camera_zones).where(camera_zones.c.camera_id == camera_id)
    with engine.connect() as conn:
        return [zone_to_api(dict(r)) for r in conn.execute(stmt).mappings()]


def create_zone(engine: Engine, camera_id: UUID, body: CameraZoneCreate) -> dict[str, Any]:
    """Создать ROI-зону для камеры; вернуть её в форме API."""
    values = {
        "camera_id": camera_id,
        "zone_type": body.zone_type.value,
        "polygon": body.polygon,
        "note": body.note,
    }
    with engine.begin() as conn:
        result = conn.execute(camera_zones.insert().values(**values))
        inserted = result.inserted_primary_key
        assert inserted is not None  # insert всегда возвращает первичный ключ
        zone_id = inserted[0]
        row = (
            conn.execute(select(camera_zones).where(camera_zones.c.id == zone_id)).mappings().one()
        )
    return zone_to_api(dict(row))


def get_zone(engine: Engine, zone_id: int) -> dict[str, Any] | None:
    """ROI-зона по id или None."""
    stmt = select(camera_zones).where(camera_zones.c.id == zone_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return zone_to_api(dict(row)) if row is not None else None


def update_zone(engine: Engine, zone_id: int, body: CameraZoneUpdate) -> dict[str, Any] | None:
    """Частично обновить ROI-зону; вернуть её или None, если зоны нет."""
    values: dict[str, Any] = {}
    if body.zone_type is not None:
        values["zone_type"] = body.zone_type.value
    if body.polygon is not None:
        values["polygon"] = body.polygon
    if body.note is not None:
        values["note"] = body.note

    with engine.begin() as conn:
        row = (
            conn.execute(select(camera_zones).where(camera_zones.c.id == zone_id))
            .mappings()
            .first()
        )
        if row is None:
            return None
        if values:
            conn.execute(update(camera_zones).where(camera_zones.c.id == zone_id).values(**values))
        merged = {**dict(row), **values}
    return zone_to_api(merged)


def delete_zone(engine: Engine, zone_id: int) -> bool:
    """Удалить ROI-зону; True если что-то удалено, иначе False."""
    with engine.begin() as conn:
        result = conn.execute(delete(camera_zones).where(camera_zones.c.id == zone_id))
    return bool(result.rowcount)
