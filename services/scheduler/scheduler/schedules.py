"""Расписания планировщика: модель записи и чтение из конфига.

Каждая запись расписания (`ScheduleEntry`) описывает периодически создаваемое
задание на видеоанализ: откуда брать видео (`source_type`/`source_ref`), какой
пайплайн запускать и с какой периодичностью. По этим записям планировщик создаёт
строки в `analysis_tasks` с `trigger=schedule` (см. docs/04_DATA_MODEL.md §5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from monitoring_shared import SourceType


class ScheduleEntry(BaseModel):
    """Одна запись расписания — периодическое задание на анализ."""

    # Уникальное имя слота расписания (для предотвращения дублей по периоду).
    name: str = Field(min_length=1)
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    pipeline: str = Field(min_length=1)
    room_id: str | None = None
    # Период повторения, минут (> 0).
    interval_min: int = Field(gt=0)
    # Параметры пайплайна (fps и пр.), попадают в analysis_tasks.params.
    params: dict[str, Any] | None = None

    @field_validator("name", "source_ref", "pipeline")
    @classmethod
    def _strip_not_empty(cls, v: str) -> str:
        """Обрезать пробелы и не допускать пустых строк после обрезки."""
        v = v.strip()
        if not v:
            raise ValueError("значение не должно быть пустым")
        return v


def parse_schedules(data: list[dict[str, Any]]) -> list[ScheduleEntry]:
    """Разобрать список словарей в записи расписания с проверкой уникальности имён."""
    entries = [ScheduleEntry(**item) for item in data]
    names = [e.name for e in entries]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"повторяющиеся имена расписаний: {sorted(duplicates)}")
    return entries


def load_schedules(path: str | Path) -> list[ScheduleEntry]:
    """Прочитать расписания из JSON-файла (список объектов ScheduleEntry).

    Отсутствие файла — это не ошибка: планировщику просто нечего делать,
    возвращаем пустой список.
    """
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("файл расписаний должен содержать JSON-массив записей")
    return parse_schedules(raw)
