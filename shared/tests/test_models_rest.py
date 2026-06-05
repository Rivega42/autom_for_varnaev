"""Проверка моделей событий/заданий/артефактов и справочников камер/порогов."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from monitoring_shared import (
    AnalysisTask,
    Artifact,
    ArtifactKind,
    Camera,
    CameraZone,
    Event,
    EventSource,
    EventType,
    Metric,
    Severity,
    SourceType,
    TaskStatus,
    TaskTrigger,
    Threshold,
    ThresholdOp,
    ZoneType,
)


def test_event_requires_message() -> None:
    """Поле message обязательно для события."""
    with pytest.raises(ValidationError):
        Event(  # type: ignore[call-arg]
            id=uuid4(),
            ts=datetime.now(UTC),
            source=EventSource.SENSORS,
            type=EventType.THRESHOLD_EXCEEDED,
            severity=Severity.WARNING,
            payload={"metric": "air_temp"},
        )


def test_event_full() -> None:
    """Событие с message и payload собирается корректно."""
    event = Event(
        id=uuid4(),
        ts=datetime.now(UTC),
        source=EventSource.SENSORS,
        type=EventType.THRESHOLD_EXCEEDED,
        room_id="room-01",
        severity=Severity.WARNING,
        message="В холодильной камере температура выше нормы",
        payload={"metric": "air_temp", "value": 8.7, "threshold": 8.0},
    )
    assert event.message
    assert event.payload["value"] == 8.7


def test_analysis_task_enums() -> None:
    """Статус и триггер задания — из перечислений."""
    task = AnalysisTask(
        id=uuid4(),
        created_at=datetime.now(UTC),
        source_type=SourceType.STREAM,
        source_ref="rtsp://cam-01/stream",
        pipeline="pose_v1",
        status=TaskStatus.QUEUED,
        trigger=TaskTrigger.SCHEDULE,
    )
    assert task.status is TaskStatus.QUEUED
    assert task.trigger is TaskTrigger.SCHEDULE


def test_artifact_threshold_camera_zone() -> None:
    """Артефакт, порог, камера и ROI-зона собираются корректно."""
    art = Artifact(
        id=uuid4(),
        created_at=datetime.now(UTC),
        kind=ArtifactKind.SCREENSHOT,
        path="/data/artifacts/x.jpg",
    )
    thr = Threshold(
        id=1, metric=Metric.AIR_TEMP, op=ThresholdOp.GT, value=8.0, severity=Severity.WARNING
    )
    cam = Camera(id=uuid4(), room_id="room-01", name="cam-01", rtsp_url="rtsp://cam-01/stream")
    zone = CameraZone(
        id=1, camera_id=cam.id, zone_type=ZoneType.TABLE, polygon=[[0.1, 0.1], [0.9, 0.9]]
    )
    assert art.kind is ArtifactKind.SCREENSHOT
    assert thr.op is ThresholdOp.GT
    assert cam.enabled is True
    assert zone.zone_type is ZoneType.TABLE
