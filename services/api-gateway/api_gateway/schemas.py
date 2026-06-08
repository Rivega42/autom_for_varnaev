"""Схемы запросов api-gateway (тела REST по docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitoring_shared import SourceType, ZoneType

# Допустимые ключи пофункциональных тумблеров видеоаналитики камеры.
ANALYTICS_FEATURES = frozenset({"pose", "actions", "uniform", "coverage"})


class AnalysisTaskCreate(BaseModel):
    """Тело POST /analysis-tasks (docs/03_API_CONTRACT.md §3.3)."""

    source_type: SourceType
    source_ref: str = Field(min_length=1)
    # В контракте поле называется `room` (внутри БД — room_id).
    room: str | None = None
    # Камера задания: по ней применяются тумблеры аналитики и ROI-зоны.
    camera_id: UUID | None = None
    pipeline: str = Field(min_length=1)
    params: dict[str, Any] | None = None


def _validate_polygon(polygon: list[list[float]]) -> list[list[float]]:
    """Проверить ROI-полигон: ≥3 вершин, каждая — [x, y] в нормированных [0..1]."""
    if len(polygon) < 3:
        raise ValueError("полигон должен содержать не менее 3 вершин")
    for point in polygon:
        if len(point) != 2:
            raise ValueError("вершина полигона — это пара [x, y]")
        for coord in point:
            if not 0.0 <= coord <= 1.0:
                raise ValueError("координаты вершин нормированы в диапазоне [0, 1]")
    return polygon


class CameraCreate(BaseModel):
    """Тело POST /cameras: завести камеру в справочнике объекта.

    `room` — id помещения (должно существовать в справочнике). `name` обязано
    совпадать с именем потока в go2rtc.yaml (по нему берётся кадр-превью).
    """

    room: str = Field(min_length=1)
    name: str = Field(min_length=1)
    rtsp_url: str = Field(min_length=1)
    enabled: bool = True
    viewpoint: dict[str, Any] | None = None


class CameraUpdate(BaseModel):
    """Тело PATCH /cameras/{id}: включение камеры и тумблеры функций аналитики."""

    enabled: bool | None = None
    # Частичное обновление флагов: {"coverage": false} выключит только покрытие.
    analytics: dict[str, bool] | None = None

    @field_validator("analytics")
    @classmethod
    def _known_features(cls, v: dict[str, bool] | None) -> dict[str, bool] | None:
        """Разрешать только известные функции аналитики."""
        if v is not None:
            unknown = set(v) - ANALYTICS_FEATURES
            if unknown:
                raise ValueError(f"неизвестные функции аналитики: {sorted(unknown)}")
        return v


class CameraZoneCreate(BaseModel):
    """Тело POST /cameras/{id}/zones: новая ROI-зона."""

    zone_type: ZoneType
    polygon: list[list[float]]
    note: str | None = None

    @field_validator("polygon")
    @classmethod
    def _check_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        return _validate_polygon(v)


class CameraZoneUpdate(BaseModel):
    """Тело PATCH /zones/{id}: частичное обновление ROI-зоны."""

    zone_type: ZoneType | None = None
    polygon: list[list[float]] | None = None
    note: str | None = None

    @field_validator("polygon")
    @classmethod
    def _check_polygon(cls, v: list[list[float]] | None) -> list[list[float]] | None:
        return _validate_polygon(v) if v is not None else None
