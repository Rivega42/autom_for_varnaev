"""Схемы запросов api-gateway (тела REST по docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from monitoring_shared import SourceType


class AnalysisTaskCreate(BaseModel):
    """Тело POST /analysis-tasks (docs/03_API_CONTRACT.md §3.3)."""

    source_type: SourceType
    source_ref: str = Field(min_length=1)
    # В контракте поле называется `room` (внутри БД — room_id).
    room: str | None = None
    pipeline: str = Field(min_length=1)
    params: dict[str, Any] | None = None
