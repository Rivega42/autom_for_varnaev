"""Проверка проводки покрытия ROI-зон в воркере (#189): coverage_report.

Воркер по camera_id задания загружает зоны, копит heat-маску движения по кадрам
и эмитит по событию coverage_report на зону. Тесты — на фейках (sqlite + numpy),
без cv2/MediaPipe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, camera_zones, metadata
from video_analytics.worker import run_once

from monitoring_shared import EventType, SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings() -> Settings:
    return Settings(log_service_url="http://log-service:8000", artifacts_dir="/tmp", fps=5)


def _insert_task_with_camera(engine: Engine, camera_id: UUID) -> UUID:
    task_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=task_id,
                created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
                source_type=SourceType.STREAM.value,
                source_ref="rtsp://media-gateway/room-01",
                room_id="room-01",
                camera_id=camera_id,
                pipeline="pose_v1",
                status=TaskStatus.QUEUED.value,
                trigger=TaskTrigger.SCHEDULE.value,
            )
        )
    return task_id


def _insert_zone(
    engine: Engine, zone_id: int, camera_id: UUID, zone_type: str, poly: list[list[float]]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            camera_zones.insert().values(
                id=zone_id, camera_id=camera_id, zone_type=zone_type, polygon=poly
            )
        )


class _NoPoseDetector:
    """Детектор без позы: изолируем расчёт покрытия от событий поз."""

    def detect(self, frame: Frame) -> None:
        return None


def _frames_with_motion_top_left() -> list[Frame]:
    """Два кадра: во втором появляется яркий блок в левом-верхнем квадранте."""
    base: Frame = np.zeros((10, 10, 3), dtype=np.uint8)
    moved: Frame = np.zeros((10, 10, 3), dtype=np.uint8)
    moved[0:5, 0:5, :] = 255  # движение в левом-верхнем квадранте
    return [base, moved]


def test_coverage_report_emitted_per_zone() -> None:
    """Зона с движением даёт высокое покрытие, зона без движения — нулевое."""
    engine = _engine()
    camera_id = uuid4()
    _insert_task_with_camera(engine, camera_id)
    # Левый-верхний квадрант (там движение) и правый-нижний (там пусто).
    _insert_zone(engine, 1, camera_id, "table", [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]])
    _insert_zone(engine, 2, camera_id, "floor", [[0.5, 0.5], [1, 0.5], [1, 1], [0.5, 1]])

    sink = CollectingEventSink()
    source: FrameSource = FakeFrameSource(_frames_with_motion_top_left())

    processed = run_once(
        engine,
        _settings(),
        detector=_NoPoseDetector(),
        sink=sink,
        source_factory=lambda *_: source,
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )

    assert processed
    coverage = [e for e in sink.events if e.type is EventType.COVERAGE_REPORT]
    assert len(coverage) == 2, "ожидаем по событию покрытия на каждую зону"
    by_zone = {e.payload["zone"]: e.payload["coverage_pct"] for e in coverage}
    assert by_zone["table"] > 50, "в зоне с движением покрытие должно быть высоким"
    assert by_zone["floor"] == 0, "в зоне без движения покрытие нулевое"


def test_no_zones_no_coverage() -> None:
    """Без зон (камера без ROI) события покрытия не эмитятся."""
    engine = _engine()
    camera_id = uuid4()
    _insert_task_with_camera(engine, camera_id)  # зоны не заводим

    sink = CollectingEventSink()
    run_once(
        engine,
        _settings(),
        detector=_NoPoseDetector(),
        sink=sink,
        source_factory=lambda *_: FakeFrameSource(_frames_with_motion_top_left()),
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )

    assert not any(e.type is EventType.COVERAGE_REPORT for e in sink.events)
