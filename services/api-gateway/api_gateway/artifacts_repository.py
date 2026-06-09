"""Доступ к артефактам-доказательствам (таблица artifacts) из api-gateway.

Чтение метаданных артефакта (путь, mime) для отдачи файла наружу и запись
метаданных снимка браузерного живого анализа. Сами файлы — на общем томе
(см. artifacts_store).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select

from api_gateway.tables import artifacts
from monitoring_shared import Artifact


def get_artifact(engine: Engine, artifact_id: UUID) -> dict[str, Any] | None:
    """Метаданные артефакта по id или None, если его нет."""
    stmt = select(artifacts).where(artifacts.c.id == artifact_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row is not None else None


def insert_artifact(engine: Engine, artifact: Artifact) -> None:
    """Записать метаданные артефакта в таблицу artifacts."""
    with engine.begin() as conn:
        conn.execute(
            artifacts.insert().values(
                id=artifact.id,
                created_at=artifact.created_at,
                kind=artifact.kind.value,
                path=artifact.path,
                mime=artifact.mime,
                room_id=artifact.room_id,
                camera_id=artifact.camera_id,
                task_id=artifact.task_id,
                meta=artifact.meta,
            )
        )
