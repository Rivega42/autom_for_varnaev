"""Доступ к данным контроля присутствия (#300): правила и последние присутствия.

Правила — таблица presence_rules (LEFT JOIN rooms для имени помещения).
«Последнее присутствие» помещения — последнее событие presence_detected (#302)
по room_id. Из БД берётся только разумное окно (сутки): более старые события
для дневных окон всё равно означают отсутствие.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select

from scheduler.presence_control import PresenceRule
from scheduler.tables import events, presence_rules, rooms


def load_presence_rules(engine: Engine) -> list[PresenceRule]:
    """Включённые правила контроля присутствия с именем помещения."""
    stmt = (
        select(presence_rules, rooms.c.name.label("room_name"))
        .select_from(presence_rules.outerjoin(rooms, presence_rules.c.room_id == rooms.c.id))
        .where(presence_rules.c.enabled.is_(True))
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        PresenceRule(
            id=r["id"],
            room_id=r["room_id"],
            window_start=r["window_start"],
            window_end=r["window_end"],
            max_absence_min=r["max_absence_min"],
            room_name=r["room_name"],
        )
        for r in rows
    ]


def load_last_presence(engine: Engine, now: datetime) -> dict[str, datetime]:
    """Последний presence_detected по каждому помещению за последние сутки."""
    cutoff = now - timedelta(hours=24)
    stmt = (
        select(events.c.ts, events.c.room_id)
        .where(events.c.type == "presence_detected")
        .where(events.c.ts >= cutoff)
        .order_by(events.c.ts)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    last: dict[str, datetime] = {}
    for ts, room_id in rows:
        if not room_id:
            continue
        if ts.tzinfo is None:  # SQLite может вернуть naive — трактуем как UTC
            ts = ts.replace(tzinfo=UTC)
        prev = last.get(room_id)
        if prev is None or ts >= prev:
            last[room_id] = ts
    return last
