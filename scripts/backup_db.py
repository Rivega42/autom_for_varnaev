#!/usr/bin/env python3
"""Резервное копирование БД по расписанию с ротацией (#267).

На объекте нет администратора БД, а потеря журнала санитарии/показаний
недопустима. Скрипт делает `pg_dump` в каталог бэкапов (gzip), оставляет N
последних дампов и спит до следующего раза. Запускается контейнером `backup`
(см. docker-compose). Параметры — из окружения (POSTGRES_*, BACKUP_*).

Восстановление (docs/09): `gunzip -c <дамп>.sql.gz | psql "$DSN"`.
"""

from __future__ import annotations

import gzip
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, cast

logger = logging.getLogger("backup")

_PREFIX = "monitoring-"
_SUFFIX = ".sql.gz"


def backup_filename(db: str, now: datetime) -> str:
    """Имя файла дампа: monitoring-<db>-<YYYYmmdd-HHMMSS>.sql.gz (сортируется по времени)."""
    return f"{_PREFIX}{db}-{now:%Y%m%d-%H%M%S}{_SUFFIX}"


def prune_old(backup_dir: str, keep: int) -> list[str]:
    """Оставить `keep` новейших дампов, остальные удалить; вернуть удалённые имена.

    `keep <= 0` — ротация выключена (ничего не удаляем). Сортировка по имени
    эквивалентна сортировке по времени (timestamp в имени).
    """
    if keep <= 0:
        return []
    base = Path(backup_dir)
    dumps = sorted(
        (p for p in base.glob(f"{_PREFIX}*{_SUFFIX}") if p.is_file()),
        key=lambda p: p.name,
    )
    to_remove = dumps[:-keep] if len(dumps) > keep else []
    removed: list[str] = []
    for p in to_remove:
        p.unlink(missing_ok=True)
        removed.append(p.name)
    return removed


def run_pg_dump(env: dict[str, str], target: Path) -> None:
    """Выполнить pg_dump и записать сжатый дамп в `target` (атомарно через .part)."""
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "-h",
        env.get("POSTGRES_HOST", "db"),
        "-p",
        env.get("POSTGRES_PORT", "5432"),
        "-U",
        env.get("POSTGRES_USER", "monitoring"),
        env.get("POSTGRES_DB", "monitoring"),
    ]
    proc_env = {**os.environ, "PGPASSWORD": env.get("POSTGRES_PASSWORD", "")}
    tmp = target.with_suffix(target.suffix + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    # pg_dump → stdout → gzip-файл; ошибки pg_dump падают на check=True.
    with gzip.open(tmp, "wb") as gz:
        subprocess.run(cmd, env=proc_env, stdout=cast(IO[bytes], gz), check=True)
    tmp.rename(target)  # появляется только готовый файл


def backup_once(env: dict[str, str], backup_dir: str, keep: int, now: datetime) -> Path:
    """Сделать один дамп и проредить старые; вернуть путь к дампу."""
    target = Path(backup_dir) / backup_filename(env.get("POSTGRES_DB", "monitoring"), now)
    run_pg_dump(env, target)
    removed = prune_old(backup_dir, keep)
    logger.info("Бэкап создан: %s; удалено старых: %d", target.name, len(removed))
    return target


def main() -> None:
    """Цикл: дамп → ротация → сон на BACKUP_INTERVAL_H часов (минимум 1)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    backup_dir = os.getenv("BACKUP_DIR", "/backups")
    keep = int(os.getenv("BACKUP_KEEP", "14"))
    interval_h = max(1, int(os.getenv("BACKUP_INTERVAL_H", "24")))
    keys = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    env = {k: os.getenv(k, "") for k in keys}
    logger.info(
        "Бэкап БД запущен: каталог=%s, хранить=%d, интервал=%d ч", backup_dir, keep, interval_h
    )
    while True:
        try:
            backup_once(env, backup_dir, keep, datetime.now(UTC))
        except Exception:
            logger.exception("Бэкап не удался — повтор через интервал")
        if os.getenv("BACKUP_ONCE") == "1":  # для ручного однократного запуска
            return
        time.sleep(interval_h * 3600)


if __name__ == "__main__":
    main()
