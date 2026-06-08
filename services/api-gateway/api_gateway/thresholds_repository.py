"""Доступ к таблице порогов (thresholds) из api-gateway.

Пороги задают критерии событий датчиков (threshold_exceeded/back_to_normal) и
порог «тишины» узла. Настраиваются через веб-интерфейс; воркер ingest-sensors
перечитывает их периодически.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, delete, insert, select, update

from api_gateway.schemas import ThresholdCreate, ThresholdUpdate
from api_gateway.tables import thresholds


def threshold_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку thresholds в форму ответа API."""
    return {
        "id": row["id"],
        "room": row["room_id"],
        "metric": row["metric"],
        "op": row["op"],
        "value": row["value"],
        "severity": row["severity"],
        "silent_min": row["silent_min"],
        "enabled": bool(row["enabled"]),
    }


def list_thresholds(engine: Engine) -> list[dict[str, Any]]:
    """Все пороги."""
    with engine.connect() as conn:
        return [threshold_to_api(dict(r)) for r in conn.execute(select(thresholds)).mappings()]


def create_threshold(engine: Engine, body: ThresholdCreate) -> dict[str, Any]:
    """Создать порог; вернуть его в форме API."""
    values = {
        "room_id": body.room,
        "metric": body.metric.value,
        "op": body.op.value,
        "value": body.value,
        "severity": body.severity.value,
        "silent_min": body.silent_min,
        "enabled": body.enabled,
    }
    with engine.begin() as conn:
        result = conn.execute(insert(thresholds).values(**values))
        inserted = result.inserted_primary_key
        if inserted is None:
            raise RuntimeError("БД не вернула id созданного порога")
        row = (
            conn.execute(select(thresholds).where(thresholds.c.id == inserted[0])).mappings().one()
        )
    return threshold_to_api(dict(row))


def update_threshold(
    engine: Engine, threshold_id: int, body: ThresholdUpdate
) -> dict[str, Any] | None:
    """Частично обновить порог; вернуть его или None, если не найден."""
    data = body.model_dump(exclude_unset=True)
    values: dict[str, Any] = {}
    if "room" in data:
        values["room_id"] = data["room"]
    for field in ("metric", "op", "severity"):
        if field in data and data[field] is not None:
            values[field] = data[field].value if hasattr(data[field], "value") else data[field]
    for field in ("value", "silent_min", "enabled"):
        if field in data:
            values[field] = data[field]

    with engine.begin() as conn:
        row = (
            conn.execute(select(thresholds).where(thresholds.c.id == threshold_id))
            .mappings()
            .first()
        )
        if row is None:
            return None
        if values:
            conn.execute(update(thresholds).where(thresholds.c.id == threshold_id).values(**values))
        merged = {**dict(row), **values}
    return threshold_to_api(merged)


def delete_threshold(engine: Engine, threshold_id: int) -> bool:
    """Удалить порог; True, если строка была удалена."""
    with engine.begin() as conn:
        result = conn.execute(delete(thresholds).where(thresholds.c.id == threshold_id))
    return bool(result.rowcount)
