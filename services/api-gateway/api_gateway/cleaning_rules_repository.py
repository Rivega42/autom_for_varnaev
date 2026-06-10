"""Доступ к правилам санитарного контроля уборки (cleaning_rules) из api-gateway.

Правила настраиваются через интерфейс; планировщик перечитывает их на каждом
тике и эмитит cleaning_overdue при нарушении (#265).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from api_gateway.schemas import CleaningRuleCreate, CleaningRuleUpdate
from api_gateway.tables import cleaning_rules


class DuplicateCleaningRuleError(Exception):
    """Правило для этой зоны (помещение+тип) уже существует."""


def rule_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку cleaning_rules в форму ответа API."""
    return {
        "id": row["id"],
        "room": row["room_id"],
        "zone_type": row["zone_type"],
        "interval_hours": row["interval_hours"],
        "min_coverage_pct": row["min_coverage_pct"],
        "zone_name": row["zone_name"],
        "enabled": bool(row["enabled"]),
    }


def list_rules(engine: Engine) -> list[dict[str, Any]]:
    """Все правила контроля уборки."""
    with engine.connect() as conn:
        return [rule_to_api(dict(r)) for r in conn.execute(select(cleaning_rules)).mappings()]


def create_rule(engine: Engine, body: CleaningRuleCreate) -> dict[str, Any]:
    """Создать правило; на дубль зоны — DuplicateCleaningRuleError."""
    values = {
        "room_id": body.room,
        "zone_type": body.zone_type.value,
        "interval_hours": body.interval_hours,
        "min_coverage_pct": body.min_coverage_pct,
        "zone_name": body.zone_name,
        "enabled": body.enabled,
    }
    try:
        with engine.begin() as conn:
            result = conn.execute(insert(cleaning_rules).values(**values))
            inserted = result.inserted_primary_key
            if inserted is None:
                raise RuntimeError("БД не вернула id созданного правила")
            row = (
                conn.execute(select(cleaning_rules).where(cleaning_rules.c.id == inserted[0]))
                .mappings()
                .one()
            )
    except IntegrityError as exc:
        raise DuplicateCleaningRuleError(f"{body.room}/{body.zone_type.value}") from exc
    return rule_to_api(dict(row))


def update_rule(engine: Engine, rule_id: int, body: CleaningRuleUpdate) -> dict[str, Any] | None:
    """Частично обновить правило; None — если правила нет."""
    values: dict[str, Any] = {}
    if body.interval_hours is not None:
        values["interval_hours"] = body.interval_hours
    if body.min_coverage_pct is not None:
        values["min_coverage_pct"] = body.min_coverage_pct
    if body.zone_name is not None:
        values["zone_name"] = body.zone_name
    if body.enabled is not None:
        values["enabled"] = body.enabled

    with engine.begin() as conn:
        row = (
            conn.execute(select(cleaning_rules).where(cleaning_rules.c.id == rule_id))
            .mappings()
            .first()
        )
        if row is None:
            return None
        if values:
            conn.execute(
                update(cleaning_rules).where(cleaning_rules.c.id == rule_id).values(**values)
            )
        merged = {**dict(row), **values}
    return rule_to_api(merged)


def delete_rule(engine: Engine, rule_id: int) -> bool:
    """Удалить правило; True если что-то удалено."""
    with engine.begin() as conn:
        result = conn.execute(delete(cleaning_rules).where(cleaning_rules.c.id == rule_id))
    return bool(result.rowcount)
