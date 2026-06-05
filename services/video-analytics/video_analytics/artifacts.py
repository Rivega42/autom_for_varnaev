"""Сохранение артефактов-доказательств (скриншоты, keypoints/coverage).

Файлы кладутся на общий том по схеме /data/artifacts/<YYYY-MM-DD>/<id>.<ext>
(docs/01 §6); метаданные пишутся в таблицу artifacts (docs/04 §6). Кодирование
изображения (cv2) — runtime; запись JSON и путь — на чистом stdlib (тестируемо).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from monitoring_shared import Artifact
from video_analytics.sources import Frame
from video_analytics.tables import artifacts


def build_artifact_path(artifacts_dir: str, ts: datetime, artifact_id: UUID, ext: str) -> str:
    """Путь артефакта по схеме /<dir>/<YYYY-MM-DD>/<id>.<ext>."""
    return f"{artifacts_dir}/{ts:%Y-%m-%d}/{artifact_id}.{ext}"


def save_keypoints_json(path: str, payload: dict[str, Any]) -> None:
    """Сохранить keypoints/coverage в JSON (UTF-8, без ASCII-эскейпа)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def save_screenshot(frame: Frame, path: str) -> None:
    """Сохранить кадр-скриншот (кодирование через OpenCV — runtime)."""
    import cv2

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(path, frame)


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
