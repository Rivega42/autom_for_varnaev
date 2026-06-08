"""Доступ к таблице расписаний (schedules) из api-gateway.

Расписания задают периодический запуск видеоанализа (таймер). Настраиваются
через веб-интерфейс; воркер scheduler перечитывает их каждый тик.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, delete, insert, select, update

from api_gateway.schemas import ScheduleCreate, ScheduleUpdate
from api_gateway.tables import schedules


def schedule_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку schedules в форму ответа API."""
    return {
        "id": row["id"],
        "name": row["name"],
        "source_type": row["source_type"],
        "source_ref": row["source_ref"],
        "room": row["room_id"],
        "camera_id": str(row["camera_id"]) if row.get("camera_id") else None,
        "pipeline": row["pipeline"],
        "params": row["params"],
        "interval_min": row["interval_min"],
        "enabled": bool(row["enabled"]),
    }


def list_schedules(engine: Engine) -> list[dict[str, Any]]:
    """Все расписания."""
    with engine.connect() as conn:
        return [schedule_to_api(dict(r)) for r in conn.execute(select(schedules)).mappings()]


def create_schedule(engine: Engine, body: ScheduleCreate) -> dict[str, Any]:
    """Создать расписание; вернуть его в форме API."""
    values = {
        "name": body.name,
        "source_type": body.source_type.value,
        "source_ref": body.source_ref,
        "room_id": body.room,
        "camera_id": body.camera_id,
        "pipeline": body.pipeline,
        "params": body.params,
        "interval_min": body.interval_min,
        "enabled": body.enabled,
    }
    with engine.begin() as conn:
        result = conn.execute(insert(schedules).values(**values))
        inserted = result.inserted_primary_key
        if inserted is None:
            raise RuntimeError("БД не вернула id созданного расписания")
        row = conn.execute(select(schedules).where(schedules.c.id == inserted[0])).mappings().one()
    return schedule_to_api(dict(row))


def update_schedule(
    engine: Engine, schedule_id: int, body: ScheduleUpdate
) -> dict[str, Any] | None:
    """Частично обновить расписание; вернуть его или None, если не найдено."""
    data = body.model_dump(exclude_unset=True)
    values: dict[str, Any] = {}
    if "room" in data:
        values["room_id"] = data["room"]
    if "source_type" in data and data["source_type"] is not None:
        values["source_type"] = data["source_type"].value
    for field in (
        "name",
        "source_ref",
        "camera_id",
        "pipeline",
        "params",
        "interval_min",
        "enabled",
    ):
        if field in data:
            values[field] = data[field]

    with engine.begin() as conn:
        row = (
            conn.execute(select(schedules).where(schedules.c.id == schedule_id)).mappings().first()
        )
        if row is None:
            return None
        if values:
            conn.execute(update(schedules).where(schedules.c.id == schedule_id).values(**values))
        merged = {**dict(row), **values}
    return schedule_to_api(merged)


def delete_schedule(engine: Engine, schedule_id: int) -> bool:
    """Удалить расписание; True, если строка была удалена."""
    with engine.begin() as conn:
        result = conn.execute(delete(schedules).where(schedules.c.id == schedule_id))
    return bool(result.rowcount)
