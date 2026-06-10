"""Доступ к таблице events (запись/чтение)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, and_, func, select
from sqlalchemy.engine import RowMapping

from log_service.tables import events
from monitoring_shared import Event


def insert_event(engine: Engine, event: Event) -> None:
    """Записать событие в таблицу events."""
    with engine.begin() as conn:
        conn.execute(
            events.insert().values(
                id=event.id,
                ts=event.ts,
                source=event.source.value,
                type=event.type.value,
                room_id=event.room_id,
                severity=event.severity.value,
                message=event.message,
                payload=event.payload,
                artifact_id=event.artifact_id,
                task_id=event.task_id,
            )
        )


def _to_item(row: RowMapping) -> dict[str, Any]:
    """Преобразовать строку events в элемент ответа API (docs/03 §3.2)."""
    acked = row.get("acknowledged_at")
    return {
        "id": str(row["id"]),
        "ts": row["ts"].isoformat() if row["ts"] is not None else None,
        "source": row["source"],
        "type": row["type"],
        "room": row["room_id"],
        "severity": row["severity"],
        "message": row["message"],
        "payload": row["payload"],
        # путь к артефакту резолвится позже (через artifacts); в v1 — null
        "artifact_path": None,
        # подтверждение оператором (#264); null = не подтверждено
        "acknowledged_at": acked.isoformat() if acked is not None else None,
    }


def ack_event(engine: Engine, event_id: UUID, now: datetime) -> bool:
    """Подтвердить событие (идемпотентно); False — события нет."""
    with engine.begin() as conn:
        row = conn.execute(select(events.c.id).where(events.c.id == event_id)).first()
        if row is None:
            return False
        conn.execute(
            events.update()
            .where(events.c.id == event_id, events.c.acknowledged_at.is_(None))
            .values(acknowledged_at=now)
        )
    return True


def find_for_escalation(
    engine: Engine,
    *,
    severities: tuple[str, ...],
    older_than: datetime,
    repeat_after: datetime,
    max_count: int,
) -> list[RowMapping]:
    """Неподтверждённые события для повторного уведомления.

    Условия: важность из списка; событие старше `older_than`; ещё не
    эскалировалось ЛИБО последняя эскалация раньше `repeat_after`; повторов
    меньше `max_count`.
    """
    stmt = select(events).where(
        events.c.acknowledged_at.is_(None),
        events.c.severity.in_(severities),
        events.c.ts <= older_than,
        events.c.escalation_count < max_count,
        (events.c.escalated_at.is_(None)) | (events.c.escalated_at <= repeat_after),
    )
    with engine.connect() as conn:
        return list(conn.execute(stmt).mappings())


def mark_escalated(engine: Engine, event_id: UUID, now: datetime) -> None:
    """Зафиксировать факт повторного уведомления."""
    with engine.begin() as conn:
        conn.execute(
            events.update()
            .where(events.c.id == event_id)
            .values(escalated_at=now, escalation_count=events.c.escalation_count + 1)
        )


def list_events(
    engine: Engine,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    type_: str | None = None,
    room: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Выбрать события с фильтрами и пагинацией; вернуть (items, total)."""
    conditions = []
    if from_ts is not None:
        conditions.append(events.c.ts >= from_ts)
    if to_ts is not None:
        conditions.append(events.c.ts <= to_ts)
    if type_ is not None:
        conditions.append(events.c.type == type_)
    if room is not None:
        conditions.append(events.c.room_id == room)

    where = and_(*conditions) if conditions else None

    items_stmt = select(events).order_by(events.c.ts.desc()).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(events)
    if where is not None:
        items_stmt = items_stmt.where(where)
        count_stmt = count_stmt.where(where)

    with engine.connect() as conn:
        rows = conn.execute(items_stmt).mappings().all()
        total = conn.execute(count_stmt).scalar_one()
    return [_to_item(r) for r in rows], total


def get_event(engine: Engine, event_id: UUID) -> dict[str, Any] | None:
    """Вернуть одно событие по id или None, если не найдено."""
    stmt = select(events).where(events.c.id == event_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return _to_item(row) if row is not None else None
