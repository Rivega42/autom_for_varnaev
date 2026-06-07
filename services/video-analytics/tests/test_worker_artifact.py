"""Проверка сохранения скриншот-артефакта задания в воркере (#188).

При появлении событий воркер сохраняет один кадр-доказательство (инъекция
`save_frame`, без cv2) и пишет строку в `artifacts` с task_id и путём по схеме.
Без событий — артефакта нет.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from video_analytics.config import Settings
from video_analytics.event_sink import CollectingEventSink
from video_analytics.landmarks import Landmark, PoseLandmark, PoseResult
from video_analytics.sources import FakeFrameSource, Frame, FrameSource
from video_analytics.tables import analysis_tasks, metadata
from video_analytics.worker import run_once

from monitoring_shared import SourceType, TaskStatus, TaskTrigger


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _settings() -> Settings:
    return Settings(
        log_service_url="http://log-service:8000", artifacts_dir="/data/artifacts", fps=5
    )


def _insert_task(engine: Engine) -> UUID:
    task_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            analysis_tasks.insert().values(
                id=task_id,
                created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
                source_type=SourceType.FILE.value,
                source_ref="/data/clip.mp4",
                room_id="room-01",
                pipeline="pose_v1",
                status=TaskStatus.QUEUED.value,
                trigger=TaskTrigger.SCHEDULE.value,
            )
        )
    return task_id


def _pose_right_arm_up() -> PoseResult:
    lms = [Landmark(0.5, 0.5, 1.0) for _ in range(33)]
    lms[int(PoseLandmark.RIGHT_WRIST)] = Landmark(0.5, 0.2, 1.0)
    return PoseResult(lms)


class _Detector:
    def __init__(self, pose: PoseResult | None) -> None:
        self._pose = pose

    def detect(self, frame: Frame) -> PoseResult | None:
        return self._pose


def _frames(n: int) -> list[Frame]:
    frame: Frame = np.zeros((4, 4, 3), dtype=np.uint8)
    return [frame for _ in range(n)]


def test_screenshot_saved_on_events() -> None:
    """Есть события → один скриншот сохранён и записан в artifacts с task_id и путём."""
    engine = _engine()
    task_id = _insert_task(engine)
    saved: list[str] = []
    source: FrameSource = FakeFrameSource(_frames(3))

    run_once(
        engine,
        _settings(),
        detector=_Detector(_pose_right_arm_up()),
        sink=CollectingEventSink(),
        source_factory=lambda *_: source,
        save_frame=lambda _frame, path: saved.append(path),
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )

    # Кадр сохранён ровно один раз (один артефакт на задание).
    assert len(saved) == 1
    with engine.connect() as conn:
        row = conn.execute(text("SELECT kind, path, task_id FROM artifacts")).fetchone()
    assert row is not None
    assert row[0] == "screenshot"
    assert row[1] == saved[0]
    # Путь по схеме /<dir>/<YYYY-MM-DD>/<id>.jpg.
    assert row[1].startswith("/data/artifacts/2026-06-06/")
    assert row[1].endswith(".jpg")
    assert UUID(str(row[2])) == task_id


def test_no_artifact_without_events() -> None:
    """Нет событий (поза не найдена) → артефакт не сохраняется и не пишется."""
    engine = _engine()
    _insert_task(engine)
    saved: list[str] = []

    run_once(
        engine,
        _settings(),
        detector=_Detector(None),
        sink=CollectingEventSink(),
        source_factory=lambda *_: FakeFrameSource(_frames(3)),
        save_frame=lambda _frame, path: saved.append(path),
        now_fn=lambda: datetime(2026, 6, 6, 10, 5, tzinfo=UTC),
    )

    assert saved == []
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM artifacts")).scalar_one()
    assert count == 0
