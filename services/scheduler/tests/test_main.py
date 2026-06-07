"""Проверка демона-планировщика: один тик, дедуп и цикл run_forever."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scheduler.config import Settings
from scheduler.main import run_forever, tick_once
from scheduler.tables import analysis_tasks, metadata
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.pool import StaticPool


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings(tmp_path: Path) -> Settings:
    """Расписание с одной записью (период 30 минут) в временном JSON-файле."""
    path = tmp_path / "schedules.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "room-01-pose",
                    "source_type": "stream",
                    "source_ref": "rtsp://cam-01/stream",
                    "pipeline": "pose_v1",
                    "room_id": "room-01",
                    "interval_min": 30,
                }
            ]
        ),
        encoding="utf-8",
    )
    return Settings(schedules_path=str(path), tick_interval_s=60)


def _task_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(analysis_tasks)).scalar_one())


def test_tick_once_creates_task(tmp_path: Path) -> None:
    """Один тик читает расписания и создаёт задание."""
    engine = _engine()
    settings = _settings(tmp_path)
    created = tick_once(engine, settings, datetime(2026, 6, 6, 10, 0, tzinfo=UTC))
    assert created == 1
    assert _task_count(engine) == 1


def test_tick_once_dedup_same_slot(tmp_path: Path) -> None:
    """Повторный тик в том же слоте не создаёт второе задание."""
    engine = _engine()
    settings = _settings(tmp_path)
    now = datetime(2026, 6, 6, 10, 0, tzinfo=UTC)
    assert tick_once(engine, settings, now) == 1
    assert tick_once(engine, settings, now + timedelta(minutes=1)) == 0
    assert _task_count(engine) == 1


def test_run_forever_max_iterations(tmp_path: Path) -> None:
    """Цикл выполняет заданное число тиков и спит между ними."""
    engine = _engine()
    settings = _settings(tmp_path)
    sleeps: list[float] = []
    times = iter(
        [
            datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
            datetime(2026, 6, 6, 10, 40, tzinfo=UTC),  # следующий слот (период 30 мин)
        ]
    )
    run_forever(
        engine,
        settings,
        sleep=sleeps.append,
        now_fn=lambda: next(times),
        max_iterations=2,
    )
    # Два разных слота → два задания; между двумя тиками ровно один сон.
    assert _task_count(engine) == 2
    assert sleeps == [60]
