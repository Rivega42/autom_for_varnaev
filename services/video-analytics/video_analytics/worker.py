"""Воркер video-analytics: обработка одного задания и выбор задания из очереди.

`process_task` прогоняет кадры источника через детектор поз и анализаторы
(простые позы + составные действия), отправляя события в сток (log-service).
`run_once` берёт одно задание из очереди, обрабатывает его и проставляет статус.
Тяжёлые зависимости (MediaPipe, OpenCV) изолированы за интерфейсами — логика
воркера тестируется на фейках. См. docs/07_VIDEO_ANALYTICS.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine

from monitoring_shared import AnalysisTask, Artifact, ArtifactKind, SourceType
from video_analytics.actions import CompositeActionAnalyzer, build_action_event
from video_analytics.artifacts import build_artifact_path, insert_artifact, save_screenshot
from video_analytics.config import Settings
from video_analytics.detector import PoseDetector
from video_analytics.event_sink import EventSink
from video_analytics.landmarks import PoseLandmark
from video_analytics.pose_events import SimplePoseAnalyzer, build_pose_event
from video_analytics.repository import claim_next_task, mark_done, mark_failed
from video_analytics.sources import Frame, FrameSource
from video_analytics.uniform import (
    build_condition_flagged,
    is_white_coat,
    mean_brightness_saturation,
    torso_polygon,
)

logger = logging.getLogger(__name__)

# Точки торса для эвристики «белого халата» (плечи и бёдра).
_TORSO_LANDMARKS = (
    PoseLandmark.LEFT_SHOULDER,
    PoseLandmark.RIGHT_SHOULDER,
    PoseLandmark.LEFT_HIP,
    PoseLandmark.RIGHT_HIP,
)

# Фабрика источника кадров по (тип, ссылка, целевой fps) — для подмены в тестах.
SourceFactory = Callable[[SourceType, str, int], FrameSource]

# Сохранение кадра-скриншота (кадр, путь) — инъекция для тестов без OpenCV.
ScreenshotSaver = Callable[[Frame, str], None]


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


def process_task(
    task: AnalysisTask,
    *,
    engine: Engine,
    settings: Settings,
    source: FrameSource,
    detector: PoseDetector,
    sink: EventSink,
    now_fn: Callable[[], datetime] = _now_utc,
    save_frame: ScreenshotSaver = save_screenshot,
) -> dict[str, Any]:
    """Прогнать кадры задания через детектор и анализаторы, отправить события.

    Для первого кадра, породившего события, сохраняется скриншот-доказательство
    на общий том и пишется строка `artifacts` (один артефакт на задание).
    Возвращает сводку (frames/poses/events/artifact) для `analysis_tasks.result`.
    Источник кадров закрывается в любом случае.
    """
    poses = SimplePoseAnalyzer()
    actions = CompositeActionAnalyzer()
    frames = 0
    poses_found = 0
    events_sent = 0
    # Флаг «нет спецодежды» эмитим однократно на задание (антиспам).
    uniform_flagged = False
    # Скриншот-доказательство сохраняем один раз на задание.
    artifact_path: str | None = None
    try:
        for frame in source.frames():
            frames += 1
            pose = detector.detect(frame)
            if pose is None:
                continue
            poses_found += 1
            ts = now_fn()
            before = events_sent
            for detection in poses.process(pose):
                sink.emit(build_pose_event(detection, task.room_id, ts))
                events_sent += 1
            for action in actions.process(pose, ts):
                sink.emit(build_action_event(action, task.room_id, ts))
                events_sent += 1
            # Эвристика «белого халата»: при видимом торсе и отсутствии халата —
            # одно событие condition_flagged на задание.
            if not uniform_flagged and all(pose.visible(lm) for lm in _TORSO_LANDMARKS):
                brightness, saturation = mean_brightness_saturation(frame, torso_polygon(pose))
                if not is_white_coat(brightness, saturation):
                    sink.emit(build_condition_flagged(brightness, saturation, task.room_id, ts))
                    events_sent += 1
                    uniform_flagged = True
            # Кадр породил события и скриншота ещё нет — сохраняем доказательство.
            if events_sent > before and artifact_path is None:
                artifact_path = _save_evidence(engine, settings, task, frame, ts, save_frame)
    finally:
        source.close()
    return {
        "frames": frames,
        "poses": poses_found,
        "events": events_sent,
        "artifact": artifact_path,
    }


def _save_evidence(
    engine: Engine,
    settings: Settings,
    task: AnalysisTask,
    frame: Frame,
    ts: datetime,
    save_frame: ScreenshotSaver,
) -> str:
    """Сохранить скриншот-доказательство на том и записать строку artifacts."""
    artifact_id = uuid4()
    path = build_artifact_path(settings.artifacts_dir, ts, artifact_id, "jpg")
    save_frame(frame, path)
    insert_artifact(
        engine,
        Artifact(
            id=artifact_id,
            created_at=ts,
            kind=ArtifactKind.SCREENSHOT,
            path=path,
            mime="image/jpeg",
            room_id=task.room_id,
            task_id=task.id,
        ),
    )
    return path


def run_once(
    engine: Engine,
    settings: Settings,
    *,
    detector: PoseDetector,
    sink: EventSink,
    source_factory: SourceFactory,
    now_fn: Callable[[], datetime] = _now_utc,
    save_frame: ScreenshotSaver = save_screenshot,
) -> bool:
    """Взять одно задание из очереди и обработать его.

    Возвращает False, если очередь пуста (заданий нет), иначе True. Ошибка
    обработки переводит задание в `failed`, но не роняет воркер.
    """
    task = claim_next_task(engine, now_fn())
    if task is None:
        return False
    logger.info("Видеоаналитика: взято задание %s (%s)", task.id, task.source_ref)
    try:
        source = source_factory(task.source_type, task.source_ref, settings.fps)
        result = process_task(
            task,
            engine=engine,
            settings=settings,
            source=source,
            detector=detector,
            sink=sink,
            now_fn=now_fn,
            save_frame=save_frame,
        )
    except Exception as exc:
        logger.exception("Видеоаналитика: задание %s завершилось ошибкой", task.id)
        mark_failed(engine, task.id, now_fn(), str(exc))
        return True
    mark_done(engine, task.id, now_fn(), result)
    logger.info("Видеоаналитика: задание %s готово: %s", task.id, result)
    return True
