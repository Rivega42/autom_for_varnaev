"""Доступ к справочнику камер (cameras) из api-gateway.

Используется интерфейсом настройки видеоаналитики: список/чтение камер и
обновление (включение камеры, пофункциональные тумблеры аналитики).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, insert, select, update

from api_gateway.schemas import CameraCreate, CameraUpdate
from api_gateway.tables import camera_zones, cameras


def camera_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку cameras в форму ответа API."""
    return {
        "id": str(row["id"]),
        "room": row["room_id"],
        "name": row["name"],
        "rtsp_url": row["rtsp_url"],
        "enabled": bool(row["enabled"]),
        # None = все функции включены по умолчанию.
        "analytics": row.get("analytics"),
    }


def list_cameras(engine: Engine) -> list[dict[str, Any]]:
    """Список активных камер (мягко удалённые скрыты, #329)."""
    stmt = select(cameras).where(cameras.c.deleted_at.is_(None))
    with engine.connect() as conn:
        return [camera_to_api(dict(r)) for r in conn.execute(stmt).mappings()]


def create_camera(engine: Engine, body: CameraCreate) -> dict[str, Any]:
    """Завести камеру в справочнике; вернуть её в форме API.

    Аналитика по умолчанию не задаётся (None = все функции включены). Камера
    появляется в веб-GUI, где настраиваются тумблеры функций и ROI-зоны.
    """
    camera_id = uuid4()
    values = {
        "id": camera_id,
        "room_id": body.room,
        "name": body.name,
        "rtsp_url": body.rtsp_url,
        "viewpoint": body.viewpoint,
        "enabled": body.enabled,
        "analytics": None,
    }
    with engine.begin() as conn:
        conn.execute(insert(cameras).values(**values))
    return camera_to_api(values)


def get_camera(engine: Engine, camera_id: UUID) -> dict[str, Any] | None:
    """Активная камера по id в форме API или None (мягко удалённая → None, #329)."""
    stmt = select(cameras).where(cameras.c.id == camera_id, cameras.c.deleted_at.is_(None))
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return camera_to_api(dict(row)) if row is not None else None


def update_camera(engine: Engine, camera_id: UUID, body: CameraUpdate) -> dict[str, Any] | None:
    """Частично обновить камеру (enabled / тумблеры analytics); вернуть её или None.

    Флаги `analytics` сливаются с текущими (частичное обновление): передать
    `{"coverage": false}` — выключить только покрытие, не трогая остальные.
    """
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(cameras).where(cameras.c.id == camera_id, cameras.c.deleted_at.is_(None))
            )
            .mappings()
            .first()
        )
        if row is None:
            return None

        values: dict[str, Any] = {}
        if body.enabled is not None:
            values["enabled"] = body.enabled
        if body.analytics is not None:
            current = dict(row.get("analytics") or {})
            current.update(body.analytics)
            values["analytics"] = current

        if values:
            conn.execute(update(cameras).where(cameras.c.id == camera_id).values(**values))
        merged = {**dict(row), **values}
    return camera_to_api(merged)


def soft_delete_camera(engine: Engine, camera_id: UUID, now: datetime) -> bool:
    """Мягко удалить камеру (#329): пометить deleted_at, выключить, убрать ROI-зоны.

    История анализа/артефактов/событий по камере СОХРАНЯЕТСЯ (доказательная база
    ППК), но камера исчезает из справочника/обзора и перестаёт опрашиваться
    планировщиком (enabled=false). ROI-зоны — это конфиг, удаляются. Возвращает
    True, если активная камера найдена и удалена; False, если её нет или она уже
    удалена.
    """
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(cameras.c.id).where(
                    cameras.c.id == camera_id, cameras.c.deleted_at.is_(None)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return False
        conn.execute(delete(camera_zones).where(camera_zones.c.camera_id == camera_id))
        conn.execute(
            update(cameras).where(cameras.c.id == camera_id).values(deleted_at=now, enabled=False)
        )
    return True
