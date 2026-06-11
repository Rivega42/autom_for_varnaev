"""Pydantic-модели общих сущностей контура.

Соответствуют таблицам из docs/04_DATA_MODEL.md. Здесь — справочники и
показания датчиков (E1.13); остальные сущности добавляются в E1.14.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Metric(StrEnum):
    """Метрики показаний датчиков (v1)."""

    AIR_TEMP = "air_temp"  # температура воздуха, °C
    HUMIDITY = "humidity"  # влажность, %
    SURFACE_IR = "surface_ir"  # бесконтактная ИК-температура поверхности, °C
    UV_INDEX = "uv_index"  # общий УФ-индекс / УФ-A (LTR390), безразмерный
    UV_C = "uv_c"  # бактерицидный УФ-C 254 нм (GUVC-S10GD), мВт/см²


class Room(BaseModel):
    """Помещение объекта (таблица rooms)."""

    id: str
    name: str
    is_cold: bool = False


class SensorNode(BaseModel):
    """Узел датчиков — контроллер (таблица sensor_nodes)."""

    id: str
    room_id: str
    placement: str | None = None
    power: str | None = None
    note: str | None = None


class Reading(BaseModel):
    """Показание датчика — точка временного ряда (таблица sensor_readings)."""

    ts: datetime
    node_id: str
    room_id: str
    metric: Metric
    value: float
    unit: str


class Severity(StrEnum):
    """Важность события/порога."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EventSource(StrEnum):
    """Источник события в едином журнале."""

    SENSORS = "sensors"
    ANALYTICS = "analytics"


class EventType(StrEnum):
    """Типы событий (docs/04_DATA_MODEL.md §4)."""

    # датчики
    THRESHOLD_EXCEEDED = "threshold_exceeded"
    SENSOR_SILENT = "sensor_silent"
    BACK_TO_NORMAL = "back_to_normal"
    # видеоаналитика
    POSE_EVENT = "pose_event"
    ACTION_DETECTED = "action_detected"
    COVERAGE_REPORT = "coverage_report"
    CONDITION_FLAGGED = "condition_flagged"
    UNIFORM_VIOLATION = "uniform_violation"
    FORBIDDEN_ZONE_ENTRY = "forbidden_zone_entry"
    PRESENCE_DETECTED = "presence_detected"
    # контроль присутствия по окну времени (#300)
    PRESENCE_MISSING = "presence_missing"
    # санитарный контроль
    CLEANING_OVERDUE = "cleaning_overdue"
    # живость инфраструктуры (камеры, медиа-шлюз, сервисы)
    CAMERA_OFFLINE = "camera_offline"
    CAMERA_ONLINE = "camera_online"
    MEDIA_GATEWAY_OFFLINE = "media_gateway_offline"
    MEDIA_GATEWAY_ONLINE = "media_gateway_online"
    SERVICE_SILENT = "service_silent"
    SERVICE_RESTORED = "service_restored"


class Event(BaseModel):
    """Событие единого журнала (таблица events)."""

    id: UUID
    ts: datetime
    source: EventSource
    type: EventType
    room_id: str | None = None
    severity: Severity
    # человекочитаемый текст для оператора (RU); машинные детали — в payload
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_id: UUID | None = None
    task_id: UUID | None = None


class SourceType(StrEnum):
    """Источник видео для задания на анализ."""

    STREAM = "stream"
    FILE = "file"


class TaskStatus(StrEnum):
    """Статус жизненного цикла задания на анализ."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskTrigger(StrEnum):
    """Источник триггера задания."""

    SCHEDULE = "schedule"
    MANUAL = "manual"
    AURA = "aura"  # СТЫК-АУРА (v2): в v1 не используется


class AnalysisTask(BaseModel):
    """Задание на видеоанализ (таблица analysis_tasks)."""

    id: UUID
    created_at: datetime
    source_type: SourceType
    source_ref: str
    room_id: str | None = None
    # камера задания: по ней берутся ROI-зоны для % покрытия (None = без покрытия)
    camera_id: UUID | None = None
    pipeline: str
    params: dict[str, Any] | None = None
    status: TaskStatus
    trigger: TaskTrigger
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    # СТЫК-АУРА (v2): webhook о готовности; в v1 не используется
    callback_url: str | None = None


class ArtifactKind(StrEnum):
    """Тип артефакта-доказательства."""

    SCREENSHOT = "screenshot"
    KEYPOINTS = "keypoints"
    COVERAGE = "coverage"
    VIDEO = "video"  # СТЫК-АУРА (v2): видеофайл от АУРА


class Artifact(BaseModel):
    """Файл-доказательство (таблица artifacts)."""

    id: UUID
    created_at: datetime
    kind: ArtifactKind
    path: str
    mime: str | None = None
    room_id: str | None = None
    camera_id: UUID | None = None
    task_id: UUID | None = None
    meta: dict[str, Any] | None = None


class ThresholdOp(StrEnum):
    """Оператор сравнения порога."""

    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="


class Threshold(BaseModel):
    """Порог метрики/«тишины» (таблица thresholds)."""

    id: int
    room_id: str | None = None  # None = глобальный порог
    metric: Metric
    op: ThresholdOp
    value: float
    severity: Severity
    silent_min: int | None = None
    enabled: bool = True


class Camera(BaseModel):
    """Камера помещения (таблица cameras)."""

    id: UUID
    room_id: str
    name: str
    rtsp_url: str
    viewpoint: dict[str, Any] | None = None
    enabled: bool = True
    # Пофункциональные тумблеры видеоаналитики камеры: {"pose","actions","uniform",
    # "coverage": bool}. None или отсутствие ключа = функция включена (по умолчанию).
    analytics: dict[str, bool] | None = None


class ZoneType(StrEnum):
    """Тип ROI-зоны камеры."""

    TABLE = "table"
    FLOOR = "floor"
    WINDOW = "window"
    FORBIDDEN = "forbidden"  # запретная зона: вход человека → событие (#299)
    WORK = "work"  # рабочая зона: присутствие человека → сигнал (#302)


class CameraZone(BaseModel):
    """ROI-зона камеры (таблица camera_zones)."""

    id: int
    camera_id: UUID
    zone_type: ZoneType
    # нормированные вершины полигона: список точек [x, y]
    polygon: list[list[float]]
    note: str | None = None
