"""Ротация артефактов: авто-очистка скриншотов старше порога (#251).

Скриншоты-доказательства копятся на томе бессрочно — без очистки диск объекта
заполнится. Раз в сутки воркер удаляет файлы старше `ARTIFACTS_RETENTION_DAYS`
и их строки в таблице artifacts. События журнала не трогаем: «висячая» ссылка
artifact_id на истёкший по сроку файл — допустимое состояние (404 от шлюза).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, delete, select

from video_analytics.tables import artifacts

logger = logging.getLogger(__name__)


def cleanup_artifacts(
    engine: Engine,
    artifacts_dir: str,
    *,
    retention_days: int,
    now: datetime,
) -> int:
    """Удалить артефакты старше `retention_days` (файлы + строки); вернуть число.

    `retention_days <= 0` — ротация выключена (ничего не делаем). Файлы удаляются
    только внутри каталога артефактов (защита от мусорных путей в БД); отсутствие
    файла не мешает удалению строки.
    """
    if retention_days <= 0:
        return 0
    cutoff = now - timedelta(days=retention_days)
    base = Path(artifacts_dir).resolve()

    stmt = select(artifacts.c.id, artifacts.c.path).where(artifacts.c.created_at < cutoff)
    with engine.connect() as conn:
        rows = list(conn.execute(stmt))
    if not rows:
        return 0

    ids = []
    for row in rows:
        ids.append(row.id)
        candidate = Path(row.path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            # путь вне каталога артефактов — строку удалим, файл не трогаем
            logger.warning("Путь артефакта вне каталога, файл пропущен: %s", row.path)
            continue
        candidate.unlink(missing_ok=True)

    with engine.begin() as conn:
        conn.execute(delete(artifacts).where(artifacts.c.id.in_(ids)))
    logger.info("Ротация артефактов: удалено %d (старше %d дн.)", len(ids), retention_days)
    return len(ids)
