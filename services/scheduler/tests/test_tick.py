"""Интеграционный тест: проход планировщика создаёт задания по расписаниям."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scheduler.schedules import load_schedules
from scheduler.tables import analysis_tasks, metadata
from scheduler.tick import run_tick
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.pool import StaticPool

from monitoring_shared import SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


_SCHEDULES = [
    {
        "name": "room-01-pose",
        "source_type": "stream",
        "source_ref": "rtsp://cam-01/stream",
        "pipeline": "pose_v1",
        "room_id": "room-01",
        "interval_min": 30,
        "params": {"fps": 5},
    },
    {
        "name": "room-02-pose",
        "source_type": "stream",
        "source_ref": "rtsp://cam-02/stream",
        "pipeline": "pose_v1",
        "room_id": "room-02",
        "interval_min": 30,
    },
]


def test_tick_creates_tasks_from_config(tmp_path: Path) -> None:
    """По расписаниям из файла создаются задания с корректными полями."""
    cfg = tmp_path / "schedules.json"
    cfg.write_text(json.dumps(_SCHEDULES), encoding="utf-8")
    entries = load_schedules(cfg)
    engine = _engine()
    now = datetime(2026, 6, 5, 10, 5, tzinfo=UTC)

    created = run_tick(engine, entries, now)
    assert len(created) == 2

    with engine.connect() as conn:
        rows = (
            conn.execute(select(analysis_tasks).order_by(analysis_tasks.c.source_ref))
            .mappings()
            .all()
        )

    assert {r["source_ref"] for r in rows} == {
        "rtsp://cam-01/stream",
        "rtsp://cam-02/stream",
    }
    first = rows[0]
    assert first["status"] == TaskStatus.QUEUED.value
    assert first["trigger"] == TaskTrigger.SCHEDULE.value
    assert first["source_type"] == SourceType.STREAM.value
    assert first["pipeline"] == "pose_v1"
    assert first["room_id"] == "room-01"


def test_tick_is_idempotent_within_slot(tmp_path: Path) -> None:
    """Повторный тик в том же слоте не плодит дубли."""
    cfg = tmp_path / "schedules.json"
    cfg.write_text(json.dumps(_SCHEDULES), encoding="utf-8")
    entries = load_schedules(cfg)
    engine = _engine()

    run_tick(engine, entries, datetime(2026, 6, 5, 10, 5, tzinfo=UTC))
    again = run_tick(engine, entries, datetime(2026, 6, 5, 10, 25, tzinfo=UTC))
    assert again == []

    with engine.connect() as conn:
        total = len(conn.execute(select(analysis_tasks)).all())
    assert total == 2
