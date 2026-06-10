"""Тесты ротации артефактов (#251): файлы+строки старше порога удаляются."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool
from video_analytics.retention import cleanup_artifacts
from video_analytics.tables import artifacts

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    artifacts.create(engine)
    return engine


def _insert(engine: Engine, path: str, created_at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            artifacts.insert().values(
                id=uuid4(),
                created_at=created_at,
                kind="screenshot",
                path=path,
                mime="image/jpeg",
            )
        )


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return len(conn.execute(select(artifacts.c.id)).all())


def test_old_artifacts_removed_fresh_kept(tmp_path: Path) -> None:
    """Старые файл+строка удаляются, свежие остаются; отсутствие файла не мешает."""
    engine = _engine()
    old_file = tmp_path / "old.jpg"
    old_file.write_bytes(b"x")
    fresh_file = tmp_path / "fresh.jpg"
    fresh_file.write_bytes(b"y")
    _insert(engine, str(old_file), NOW - timedelta(days=40))
    _insert(engine, str(tmp_path / "ghost.jpg"), NOW - timedelta(days=40))  # файла нет
    _insert(engine, str(fresh_file), NOW - timedelta(days=5))

    removed = cleanup_artifacts(engine, str(tmp_path), retention_days=30, now=NOW)

    assert removed == 2
    assert not old_file.exists()
    assert fresh_file.exists()
    assert _count(engine) == 1


def test_disabled_when_zero(tmp_path: Path) -> None:
    """retention_days=0 — ротация выключена, ничего не удаляется."""
    engine = _engine()
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    _insert(engine, str(f), NOW - timedelta(days=400))

    assert cleanup_artifacts(engine, str(tmp_path), retention_days=0, now=NOW) == 0
    assert f.exists()
    assert _count(engine) == 1


def test_path_outside_dir_row_deleted_file_kept(tmp_path: Path) -> None:
    """Путь вне каталога артефактов: строку удаляем, чужой файл не трогаем."""
    engine = _engine()
    outside = tmp_path.parent / f"outside-{uuid4().hex}.jpg"
    outside.write_bytes(b"x")
    try:
        _insert(engine, str(outside), NOW - timedelta(days=40))

        removed = cleanup_artifacts(engine, str(tmp_path / "art"), retention_days=30, now=NOW)

        assert removed == 1
        assert outside.exists()  # файл вне каталога не тронут
        assert _count(engine) == 0
    finally:
        outside.unlink(missing_ok=True)
