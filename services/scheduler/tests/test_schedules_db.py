"""Проверка загрузки расписаний из БД и слияния с файлом."""

from __future__ import annotations

from pathlib import Path

from scheduler.config import Settings
from scheduler.main import _merged_schedules
from scheduler.schedules import load_schedules_db
from scheduler.tables import metadata, schedules
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _insert(engine: Engine, name: str, *, enabled: bool = True, interval: int = 15) -> None:
    with engine.begin() as conn:
        conn.execute(
            schedules.insert().values(
                name=name,
                source_type="stream",
                source_ref="rtsp://camera.local/stream",
                room_id="room-01",
                camera_id=None,
                pipeline="pose_v1",
                params=None,
                interval_min=interval,
                enabled=enabled,
            )
        )


def test_load_db_returns_only_enabled() -> None:
    """load_schedules_db возвращает только включённые записи."""
    engine = _engine()
    _insert(engine, "вкл", enabled=True)
    _insert(engine, "выкл", enabled=False)

    entries = load_schedules_db(engine)
    assert [e.name for e in entries] == ["вкл"]
    assert entries[0].interval_min == 15


def test_merged_prefers_db_over_file(tmp_path: Path) -> None:
    """В слиянии записи файла добавляются, если имя не занято записью БД."""
    engine = _engine()
    _insert(engine, "общая")
    cfg = tmp_path / "schedules.json"
    cfg.write_text(
        '[{"name":"общая","source_type":"stream","source_ref":"rtsp://x",'
        '"pipeline":"pose_v1","interval_min":99},'
        '{"name":"только-файл","source_type":"stream","source_ref":"rtsp://y",'
        '"pipeline":"pose_v1","interval_min":20}]',
        encoding="utf-8",
    )
    settings = Settings(schedules_path=str(cfg), tick_interval_s=60)

    merged = _merged_schedules(engine, settings)
    names = sorted(e.name for e in merged)
    assert names == ["общая", "только-файл"]
    # «общая» взята из БД (interval 15), а не из файла (99)
    by_name = {e.name: e for e in merged}
    assert by_name["общая"].interval_min == 15
