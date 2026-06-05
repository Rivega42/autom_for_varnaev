"""Доступ к заданиям на анализ (analysis_tasks)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Engine, select

from monitoring_shared import AnalysisTask, CameraZone
from video_analytics.tables import analysis_tasks, camera_zones


def get_task(engine: Engine, task_id: UUID) -> AnalysisTask | None:
    """Прочитать задание по id или вернуть None."""
    stmt = select(analysis_tasks).where(analysis_tasks.c.id == task_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return AnalysisTask(**row) if row is not None else None


def load_camera_zones(engine: Engine, camera_id: UUID) -> list[CameraZone]:
    """Загрузить ROI-зоны камеры."""
    stmt = select(camera_zones).where(camera_zones.c.camera_id == camera_id)
    with engine.connect() as conn:
        return [CameraZone(**row) for row in conn.execute(stmt).mappings()]
