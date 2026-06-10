"""Тесты резервного копирования БД (#267): имя дампа, ротация, один прогон.

Обращения к pg_dump здесь не делаем (нет сервера) — проверяем чистую логику
ротации и оркестровку backup_once с подменённым run_pg_dump.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import backup_db


def _make(dir_: Path, name: str) -> Path:
    """Создать пустой файл-дамп с заданным именем и вернуть путь."""
    p = dir_ / name
    p.write_bytes(b"x")
    return p


def test_backup_filename_sortable_by_time() -> None:
    """Имя дампа содержит БД и метку времени; лексикографический порядок = хронология."""
    older = backup_db.backup_filename("monitoring", datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC))
    newer = backup_db.backup_filename("monitoring", datetime(2026, 1, 2, 9, 0, 0, tzinfo=UTC))
    assert older.startswith("monitoring-monitoring-")
    assert older.endswith(".sql.gz")
    assert older < newer  # сортировка по имени совпадает с сортировкой по времени


def test_prune_keeps_newest_n(tmp_path: Path) -> None:
    """prune_old оставляет `keep` новейших, удаляет старые и возвращает их имена."""
    names = [f"monitoring-monitoring-202601{day:02d}-000000.sql.gz" for day in range(1, 6)]
    for n in names:
        _make(tmp_path, n)
    removed = backup_db.prune_old(str(tmp_path), keep=2)
    # удалены три старейших, остались два новейших
    assert removed == names[:3]
    survivors = sorted(p.name for p in tmp_path.glob("monitoring-*.sql.gz"))
    assert survivors == names[3:]


def test_prune_disabled_when_keep_non_positive(tmp_path: Path) -> None:
    """keep <= 0 выключает ротацию — ничего не удаляется."""
    for day in range(1, 4):
        _make(tmp_path, f"monitoring-monitoring-202601{day:02d}-000000.sql.gz")
    assert backup_db.prune_old(str(tmp_path), keep=0) == []
    assert backup_db.prune_old(str(tmp_path), keep=-1) == []
    assert len(list(tmp_path.glob("monitoring-*.sql.gz"))) == 3


def test_prune_noop_when_fewer_than_keep(tmp_path: Path) -> None:
    """Если дампов меньше лимита — не удаляем ничего."""
    _make(tmp_path, "monitoring-monitoring-20260101-000000.sql.gz")
    assert backup_db.prune_old(str(tmp_path), keep=5) == []


def test_prune_ignores_foreign_files(tmp_path: Path) -> None:
    """Чужие файлы в каталоге не считаются дампами и не удаляются."""
    _make(tmp_path, "monitoring-monitoring-20260101-000000.sql.gz")
    _make(tmp_path, "monitoring-monitoring-20260102-000000.sql.gz")
    other = _make(tmp_path, "readme.txt")
    backup_db.prune_old(str(tmp_path), keep=1)
    assert other.exists()


def test_backup_once_dumps_then_prunes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """backup_once создаёт дамп через run_pg_dump и прореживает старые."""
    # Старые «дампы», которые должна снести ротация при keep=1.
    _make(tmp_path, "monitoring-monitoring-20250101-000000.sql.gz")

    def fake_dump(env: dict[str, str], target: Path) -> None:
        target.write_bytes(b"dump")

    monkeypatch.setattr(backup_db, "run_pg_dump", fake_dump)
    now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)
    result = backup_db.backup_once({"POSTGRES_DB": "monitoring"}, str(tmp_path), keep=1, now=now)
    assert result.exists()
    assert result.name == backup_db.backup_filename("monitoring", now)
    # старый снесён, остался только свежий
    assert sorted(p.name for p in tmp_path.glob("monitoring-*.sql.gz")) == [result.name]
