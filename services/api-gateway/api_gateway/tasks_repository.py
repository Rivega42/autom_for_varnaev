"""Доступ к заданиям на анализ (analysis_tasks) из api-gateway."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select

from api_gateway.schemas import AnalysisTaskCreate
from api_gateway.tables import analysis_tasks
from monitoring_shared import TaskStatus, TaskTrigger


def _iso(value: datetime | None) -> str | None:
    """Привести время к ISO-8601 UTC (naive из SQLite считаем UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def task_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку analysis_tasks в форму ответа API (room, ISO-времена)."""
    return {
        "id": str(row["id"]),
        "created_at": _iso(row["created_at"]),
        "source_type": row["source_type"],
        "source_ref": row["source_ref"],
        "room": row["room_id"],
        "camera_id": str(row["camera_id"]) if row.get("camera_id") else None,
        "pipeline": row["pipeline"],
        "params": row["params"],
        "status": row["status"],
        "trigger": row["trigger"],
        # Поля жизненного цикла на момент создания отсутствуют — берём через .get().
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
        "result": row.get("result"),
        "error": row.get("error"),
    }


def create_task(
    engine: Engine,
    body: AnalysisTaskCreate,
    now: datetime | None = None,
    trigger: TaskTrigger = TaskTrigger.MANUAL,
) -> dict[str, Any]:
    """Создать задание (status=queued); вернуть его в форме API.

    `trigger` — источник задания: MANUAL (по умолчанию, из GUI/REST) или AURA
    (разъём D.1). `body.callback_url` сохраняется для уведомления о готовности
    (D.5); для ручных заданий обычно None.
    """
    now = now or datetime.now(UTC)
    task_id = uuid4()
    values = {
        "id": task_id,
        "created_at": now,
        "source_type": body.source_type.value,
        "source_ref": body.source_ref,
        "room_id": body.room,
        "camera_id": body.camera_id,
        "pipeline": body.pipeline,
        "params": body.params,
        "status": TaskStatus.QUEUED.value,
        "trigger": trigger.value,
        "callback_url": body.callback_url,
    }
    with engine.begin() as conn:
        conn.execute(analysis_tasks.insert().values(**values))
    return task_to_api(values)


def get_task(engine: Engine, task_id: UUID) -> dict[str, Any] | None:
    """Прочитать задание по id в форме API или None."""
    stmt = select(analysis_tasks).where(analysis_tasks.c.id == task_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return task_to_api(dict(row)) if row is not None else None


def list_tasks(
    engine: Engine,
    status: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Список заданий с фильтром по статусу/времени; вернуть (items, total)."""
    conditions = []
    if status is not None:
        conditions.append(analysis_tasks.c.status == status)
    if from_ts is not None:
        conditions.append(analysis_tasks.c.created_at >= from_ts)
    if to_ts is not None:
        conditions.append(analysis_tasks.c.created_at < to_ts)

    base = select(analysis_tasks)
    # COUNT(*) на стороне БД — не выгружаем все id в память ради числа.
    count_stmt = select(func.count()).select_from(analysis_tasks)
    for cond in conditions:
        base = base.where(cond)
        count_stmt = count_stmt.where(cond)
    base = base.order_by(analysis_tasks.c.created_at.desc()).limit(limit).offset(offset)

    with engine.connect() as conn:
        items = [task_to_api(dict(r)) for r in conn.execute(base).mappings()]
        total = int(conn.execute(count_stmt).scalar_one())
    return items, total
