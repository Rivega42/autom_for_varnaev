"""Доступ к заданиям на анализ (analysis_tasks)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, select

from monitoring_shared import AnalysisTask
from video_analytics.tables import analysis_tasks


def get_task(engine: Engine, task_id: UUID) -> AnalysisTask | None:
    """Прочитать задание по id или вернуть None."""
    stmt = select(analysis_tasks).where(analysis_tasks.c.id == task_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return AnalysisTask(**row) if row is not None else None
