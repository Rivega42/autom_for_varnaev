"""Схемы запросов api-gateway (тела REST по docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from monitoring_shared import Metric, Severity, SourceType, ThresholdOp, ZoneType

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


class AnalyticsEventCreate(BaseModel):
    """Тело POST /analytics-events: событие от браузерного живого анализа.

    Браузерный анализ (live.html) шлёт распознанное событие в журнал, чтобы оно
    попало в Grafana/историю. Источник — analytics; в payload добавляется
    origin=browser (отличить от серверного). Тип — из белого списка: действия
    (`action_detected`, по умолчанию) и отчёты о покрытии (`coverage_report`,
    в payload — zone/zone_id/coverage_pct как у серверного воркера).
    """

    room: str | None = None
    message: str = Field(min_length=1)
    severity: Severity = Severity.INFO
    type: Literal["action_detected", "coverage_report"] = "action_detected"
    payload: dict[str, Any] = Field(default_factory=dict)
    # Необязательный стоп-кадр события (data-URL `data:image/jpeg;base64,…`).
    # Если задан — сохраняется как артефакт-скриншот, а событие получает
    # artifact_id и payload.artifact_url (чтобы кадр был виден в Grafana).
    image: str | None = None


class RoomCreate(BaseModel):
    """Тело POST /rooms: завести помещение в справочнике объекта.

    `id` — человекочитаемый идентификатор помещения (напр. «room-01»),
    используется как первичный ключ и в показаниях/событиях.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    # Признак холодильной/морозильной камеры (важно для холодовой цепи).
    is_cold: bool = False


class SensorNodeCreate(BaseModel):
    """Тело POST /sensor-nodes: завести узел датчиков в справочнике.

    `room_id` обязан ссылаться на существующее помещение. Без узла в справочнике
    показания этого `node_id` по MQTT отбрасываются (см. ingest-sensors).
    """

    id: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    placement: str | None = None
    power: str | None = None
    note: str | None = None


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


class ThresholdCreate(BaseModel):
    """Тело POST /thresholds: порог метрики (критерий событий датчиков)."""

    # room=None — глобальный порог (для всех помещений).
    room: str | None = None
    metric: Metric
    op: ThresholdOp
    value: float
    severity: Severity = Severity.WARNING
    silent_min: int | None = None
    enabled: bool = True


class ThresholdUpdate(BaseModel):
    """Тело PATCH /thresholds/{id}: частичное обновление порога."""

    room: str | None = None
    metric: Metric | None = None
    op: ThresholdOp | None = None
    value: float | None = None
    severity: Severity | None = None
    silent_min: int | None = None
    enabled: bool | None = None


class CleaningRuleCreate(BaseModel):
    """Тело POST /cleaning-rules: правило санитарного контроля уборки (#265).

    Зона (помещение+тип) должна убираться не реже interval_hours; покрытие
    последней уборки — не ниже min_coverage_pct (0 = не проверять покрытие).
    """

    room: str = Field(min_length=1)
    zone_type: ZoneType
    interval_hours: float = Field(gt=0)
    min_coverage_pct: int = Field(default=0, ge=0, le=100)
    zone_name: str | None = None
    enabled: bool = True


class CleaningRuleUpdate(BaseModel):
    """Тело PATCH /cleaning-rules/{id}: частичное обновление правила."""

    interval_hours: float | None = Field(default=None, gt=0)
    min_coverage_pct: int | None = Field(default=None, ge=0, le=100)
    zone_name: str | None = None
    enabled: bool | None = None


class ScheduleCreate(BaseModel):
    """Тело POST /schedules: запись расписания видеоанализа (таймер)."""

    name: str = Field(min_length=1)
    source_type: SourceType = SourceType.STREAM
    source_ref: str = Field(min_length=1)
    room: str | None = None
    camera_id: UUID | None = None
    pipeline: str = Field(min_length=1, default="pose_v1")
    params: dict[str, Any] | None = None
    interval_min: int = Field(gt=0)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    """Тело PATCH /schedules/{id}: частичное обновление расписания."""

    name: str | None = Field(default=None, min_length=1)
    source_type: SourceType | None = None
    source_ref: str | None = Field(default=None, min_length=1)
    room: str | None = None
    camera_id: UUID | None = None
    pipeline: str | None = Field(default=None, min_length=1)
    params: dict[str, Any] | None = None
    interval_min: int | None = Field(default=None, gt=0)
    enabled: bool | None = None
