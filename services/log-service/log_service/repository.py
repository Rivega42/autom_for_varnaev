"""Доступ к таблице events (запись/чтение)."""

from __future__ import annotations

from sqlalchemy import Engine

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
