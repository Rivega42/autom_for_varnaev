"""Общие модели контура мониторинга.

Единый конверт API и схемы событий/заданий/артефактов, чтобы сервисы не
расходились в форматах (см. docs/03_API_CONTRACT.md, docs/04_DATA_MODEL.md).
"""

from monitoring_shared.envelope import (
    ERROR_HTTP_STATUS,
    Envelope,
    ErrorBody,
    ErrorCode,
    error,
    ok,
)
from monitoring_shared.models import (
    AnalysisTask,
    Artifact,
    ArtifactKind,
    Camera,
    CameraZone,
    Event,
    EventSource,
    EventType,
    Metric,
    Reading,
    Room,
    SensorNode,
    Severity,
    SourceType,
    TaskStatus,
    TaskTrigger,
    Threshold,
    ThresholdOp,
    ZoneType,
)
from monitoring_shared.shutdown import install_stop_event

__version__ = "0.1.0"

__all__ = [
    "ERROR_HTTP_STATUS",
    "AnalysisTask",
    "Artifact",
    "ArtifactKind",
    "Camera",
    "CameraZone",
    "Envelope",
    "ErrorBody",
    "ErrorCode",
    "Event",
    "EventSource",
    "EventType",
    "Metric",
    "Reading",
    "Room",
    "SensorNode",
    "Severity",
    "SourceType",
    "TaskStatus",
    "TaskTrigger",
    "Threshold",
    "ThresholdOp",
    "ZoneType",
    "__version__",
    "error",
    "install_stop_event",
    "ok",
]
