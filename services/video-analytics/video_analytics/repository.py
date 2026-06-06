"""Доступ к заданиям на анализ (analysis_tasks)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, update

from monitoring_shared import AnalysisTask, CameraZone, TaskStatus
from video_analytics.tables import analysis_tasks, camera_zones


def get_task(engine: Engine, task_id: UUID) -> AnalysisTask | None:
    """Прочитать задание по id или вернуть None."""
    stmt = select(analysis_tasks).where(analysis_tasks.c.id == task_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return AnalysisTask(**row) if row is not None else None


def claim_next_task(engine: Engine, now: datetime) -> AnalysisTask | None:
    """Взять старейшее задание `queued` и атомарно перевести его в `running`.

    Возвращает задание (уже со статусом `running` и `started_at=now`) или None,
    если очередь пуста. В v1 воркер один, поэтому select+update в одной
    транзакции достаточно.
    """
    select_stmt = (
        select(analysis_tasks)
        .where(analysis_tasks.c.status == TaskStatus.QUEUED.value)
        .order_by(analysis_tasks.c.created_at)
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(select_stmt).mappings().first()
        if row is None:
            return None
        conn.execute(
            update(analysis_tasks)
            .where(analysis_tasks.c.id == row["id"])
            .values(status=TaskStatus.RUNNING.value, started_at=now)
        )
    task = AnalysisTask(**row)
    return task.model_copy(update={"status": TaskStatus.RUNNING, "started_at": now})


def load_camera_zones(engine: Engine, camera_id: UUID) -> list[CameraZone]:
    """Загрузить ROI-зоны камеры."""
    stmt = select(camera_zones).where(camera_zones.c.camera_id == camera_id)
    with engine.connect() as conn:
        return [CameraZone(**row) for row in conn.execute(stmt).mappings()]


def mark_running(engine: Engine, task_id: UUID, ts: datetime) -> None:
    """Перевести задание в running и проставить started_at."""
    stmt = (
        update(analysis_tasks)
        .where(analysis_tasks.c.id == task_id)
        .values(status=TaskStatus.RUNNING.value, started_at=ts)
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def mark_done(
    engine: Engine, task_id: UUID, ts: datetime, result: dict[str, Any] | None = None
) -> None:
    """Перевести задание в done, проставить finished_at и сводку result."""
    stmt = (
        update(analysis_tasks)
        .where(analysis_tasks.c.id == task_id)
        .values(status=TaskStatus.DONE.value, finished_at=ts, result=result)
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def mark_failed(engine: Engine, task_id: UUID, ts: datetime, error: str) -> None:
    """Перевести задание в failed, проставить finished_at и текст ошибки."""
    stmt = (
        update(analysis_tasks)
        .where(analysis_tasks.c.id == task_id)
        .values(status=TaskStatus.FAILED.value, finished_at=ts, error=error)
    )
    with engine.begin() as conn:
        conn.execute(stmt)
