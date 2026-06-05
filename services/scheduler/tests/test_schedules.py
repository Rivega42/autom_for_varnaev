"""Проверка чтения и валидации расписаний планировщика."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scheduler.config import Settings
from scheduler.schedules import ScheduleEntry, load_schedules, parse_schedules

from monitoring_shared import SourceType

_VALID = [
    {
        "name": "room-01-pose",
        "source_type": "stream",
        "source_ref": "rtsp://cam-01/stream",
        "pipeline": "pose_v1",
        "room_id": "room-01",
        "interval_min": 30,
        "params": {"fps": 5},
    }
]


def test_parse_valid_entry() -> None:
    """Корректная запись разбирается в ScheduleEntry с enum-типом источника."""
    [entry] = parse_schedules(_VALID)
    assert isinstance(entry, ScheduleEntry)
    assert entry.source_type is SourceType.STREAM
    assert entry.interval_min == 30
    assert entry.params == {"fps": 5}


def test_interval_must_be_positive() -> None:
    """Неположительный период отвергается валидацией."""
    bad = [{**_VALID[0], "interval_min": 0}]
    with pytest.raises(ValueError):
        parse_schedules(bad)


def test_empty_pipeline_rejected() -> None:
    """Пустой (после обрезки пробелов) пайплайн отвергается."""
    bad = [{**_VALID[0], "pipeline": "   "}]
    with pytest.raises(ValueError):
        parse_schedules(bad)


def test_duplicate_names_rejected() -> None:
    """Повторяющиеся имена слотов недопустимы."""
    dup = [_VALID[0], {**_VALID[0], "source_ref": "rtsp://cam-02/stream"}]
    with pytest.raises(ValueError, match="повторяющиеся имена"):
        parse_schedules(dup)


def test_load_from_file(tmp_path: Path) -> None:
    """Расписания читаются из JSON-файла на диске."""
    f = tmp_path / "schedules.json"
    f.write_text(json.dumps(_VALID), encoding="utf-8")
    entries = load_schedules(f)
    assert len(entries) == 1
    assert entries[0].name == "room-01-pose"


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    """Отсутствующий файл расписаний — пустой список, а не ошибка."""
    assert load_schedules(tmp_path / "nope.json") == []


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings.from_env даёт разумные значения по умолчанию."""
    monkeypatch.delenv("SCHEDULER_CONFIG", raising=False)
    monkeypatch.delenv("SCHEDULER_TICK_S", raising=False)
    s = Settings.from_env()
    assert s.schedules_path.endswith("schedules.json")
    assert s.tick_interval_s == 60
