"""Доступ к правилам контроля присутствия (presence_rules) из api-gateway.

Правила настраиваются через интерфейс; планировщик перечитывает их на каждом
тике и эмитит presence_missing при перерыве присутствия дольше допустимого
внутри окна (#300, #312). По паттерну cleaning_rules_repository.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from api_gateway.rooms_repository import room_exists
from api_gateway.schemas import PresenceRuleCreate, PresenceRuleUpdate
from api_gateway.tables import presence_rules


class DuplicatePresenceRuleError(Exception):
    """Правило с таким окном для этого помещения уже существует."""


class RoomNotFoundForPresenceRuleError(Exception):
    """Помещение правила отсутствует в справочнике rooms."""


def rule_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку presence_rules в форму ответа API (времена HH:MM)."""
    return {
        "id": row["id"],
        "room": row["room_id"],
        "window_start": row["window_start"].strftime("%H:%M"),
        "window_end": row["window_end"].strftime("%H:%M"),
        "max_absence_min": row["max_absence_min"],
        "enabled": bool(row["enabled"]),
    }


def list_rules(engine: Engine) -> list[dict[str, Any]]:
    """Все правила контроля присутствия."""
    with engine.connect() as conn:
        return [rule_to_api(dict(r)) for r in conn.execute(select(presence_rules)).mappings()]


def create_rule(engine: Engine, body: PresenceRuleCreate) -> dict[str, Any]:
    """Создать правило; нет помещения → RoomNotFoundForPresenceRuleError (404),
    дубль окна → DuplicatePresenceRuleError (409).

    Помещение проверяем в коде, а не FK: SQLite в тестах не форсит FK, а в
    PostgreSQL FK-нарушение дало бы IntegrityError, неотличимый от дубля.
    """
    if not room_exists(engine, body.room):
        raise RoomNotFoundForPresenceRuleError(body.room)
    values = {
        "room_id": body.room,
        "window_start": body.window_start,
        "window_end": body.window_end,
        "max_absence_min": body.max_absence_min,
        "enabled": body.enabled,
    }
    try:
        with engine.begin() as conn:
            result = conn.execute(insert(presence_rules).values(**values))
            inserted = result.inserted_primary_key
            if inserted is None:
                raise RuntimeError("БД не вернула id созданного правила")
            row = (
                conn.execute(select(presence_rules).where(presence_rules.c.id == inserted[0]))
                .mappings()
                .one()
            )
    except IntegrityError as exc:
        raise DuplicatePresenceRuleError(
            f"{body.room}/{body.window_start:%H:%M}-{body.window_end:%H:%M}"
        ) from exc
    return rule_to_api(dict(row))


def update_rule(engine: Engine, rule_id: int, body: PresenceRuleUpdate) -> dict[str, Any] | None:
    """Частично обновить правило (порог/включённость); None — если правила нет."""
    values: dict[str, Any] = {}
    if body.max_absence_min is not None:
        values["max_absence_min"] = body.max_absence_min
    if body.enabled is not None:
        values["enabled"] = body.enabled

    with engine.begin() as conn:
        row = (
            conn.execute(select(presence_rules).where(presence_rules.c.id == rule_id))
            .mappings()
            .first()
        )
        if row is None:
            return None
        if values:
            conn.execute(
                update(presence_rules).where(presence_rules.c.id == rule_id).values(**values)
            )
        merged = {**dict(row), **values}
    return rule_to_api(merged)


def delete_rule(engine: Engine, rule_id: int) -> bool:
    """Удалить правило; True если что-то удалено."""
    with engine.begin() as conn:
        result = conn.execute(delete(presence_rules).where(presence_rules.c.id == rule_id))
    return bool(result.rowcount)
