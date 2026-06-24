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


def list_artifacts(
    engine: Engine, *, limit: int = 50, camera_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Недавние артефакты-доказательства (новые сверху), опционально по камере.

    Без пути на диске — наружу отдаём только метаданные и ссылку на файл
    (URL формирует эндпойнт). Используется лентой дашборда «стены роликов».
    """
    stmt = select(
        artifacts.c.id,
        artifacts.c.created_at,
        artifacts.c.kind,
        artifacts.c.mime,
        artifacts.c.room_id,
        artifacts.c.camera_id,
        artifacts.c.task_id,
    )
    if camera_id is not None:
        stmt = stmt.where(artifacts.c.camera_id == camera_id)
    stmt = stmt.order_by(artifacts.c.created_at.desc()).limit(limit)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] is not None else None,
            "kind": r["kind"],
            "mime": r["mime"],
            "room_id": r["room_id"],
            "camera_id": str(r["camera_id"]) if r["camera_id"] is not None else None,
            "task_id": str(r["task_id"]) if r["task_id"] is not None else None,
        }
        for r in rows
    ]


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
