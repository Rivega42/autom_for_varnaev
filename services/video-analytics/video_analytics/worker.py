"""Воркер video-analytics: обработка одного задания и выбор задания из очереди.

`process_task` прогоняет кадры источника через детектор поз и анализаторы
(простые позы + составные действия + покрытие ROI-зон), отправляя события в
сток (log-service). `run_once` берёт одно задание из очереди, обрабатывает его и
проставляет статус. Тяжёлые зависимости (MediaPipe, OpenCV) изолированы за
интерфейсами — логика воркера тестируется на фейках. См. docs/07_VIDEO_ANALYTICS.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import numpy as np
from sqlalchemy import Engine

from monitoring_shared import (
    AnalysisTask,
    Artifact,
    ArtifactKind,
    Camera,
    CameraZone,
    SourceType,
)
from video_analytics.actions import CompositeActionAnalyzer, build_action_event
from video_analytics.artifacts import build_artifact_path, insert_artifact, save_screenshot
from video_analytics.config import Settings
from video_analytics.coverage import BoolMask, build_coverage_event, zone_coverage_pct
from video_analytics.detector import PoseDetector
from video_analytics.event_sink import EventSink
from video_analytics.landmarks import PoseLandmark
from video_analytics.pose_events import SimplePoseAnalyzer, build_pose_event
from video_analytics.repository import (
    claim_next_task,
    load_camera,
    load_camera_zones,
    mark_done,
    mark_failed,
)
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

# Порог межкадровой разницы (по любому каналу), выше которого пиксель — «движение».
_MOTION_THRESHOLD = 25

# Все функции аналитики выключены (для камеры с enabled=false).
_ALL_OFF = {"pose": False, "actions": False, "uniform": False, "coverage": False}

# Фабрика источника кадров по (тип, ссылка, целевой fps) — для подмены в тестах.
SourceFactory = Callable[[SourceType, str, int], FrameSource]


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


def _feature_on(flags: dict[str, bool] | None, name: str) -> bool:
    """Включена ли функция аналитики. None/отсутствие ключа = включена."""
    return True if flags is None else flags.get(name, True)


def _resolve_analytics(camera: Camera | None) -> dict[str, bool] | None:
    """Свести тумблеры аналитики камеры. Нет камеры = всё включено;
    камера выключена (enabled=false) = всё выключено; иначе — её флаги."""
    if camera is None:
        return None
    if not camera.enabled:
        return dict(_ALL_OFF)
    return camera.analytics


def _accumulate_motion(heat: BoolMask | None, prev: Frame | None, frame: Frame) -> BoolMask:
    """Дополнить heat-маску движения межкадровой разницей.

    Движение пикселя — разница с предыдущим кадром выше порога (хотя бы по одному
    каналу). На первом кадре движения ещё нет — возвращаем нулевую маску по форме
    кадра, чтобы покрытие можно было посчитать (0%) даже без движения.
    """
    if heat is None:
        heat = np.zeros(frame.shape[:2], dtype=np.bool_)
    if prev is not None:
        diff = np.abs(frame.astype(np.int16) - prev.astype(np.int16))
        motion = diff.max(axis=2) if frame.ndim == 3 else diff
        heat |= motion > _MOTION_THRESHOLD
    return heat


def process_task(
    task: AnalysisTask,
    *,
    source: FrameSource,
    detector: PoseDetector,
    sink: EventSink,
    zones: Sequence[CameraZone] = (),
    analytics: dict[str, bool] | None = None,
    engine: Engine | None = None,
    artifacts_dir: str = "",
    save_frame: Callable[[Frame, str], None] = save_screenshot,
    now_fn: Callable[[], datetime] = _now_utc,
) -> dict[str, Any]:
    """Прогнать кадры задания через детектор и анализаторы, отправить события.

    Функции аналитики включаются пофункционально через `analytics` (тумблеры
    камеры: pose/actions/uniform/coverage; None = все включены). Если переданы
    ROI-зоны (`zones`) и покрытие включено — по heat-маске движения считается %
    покрытия и эмитится `coverage_report` (один на зону). Для первого кадра с
    событиями сохраняется скриншот-доказательство (инъекция `save_frame`, запись
    в `artifacts` при заданном `engine`). Возвращает сводку; источник закрывается.
    """
    pose_on = _feature_on(analytics, "pose")
    actions_on = _feature_on(analytics, "actions")
    uniform_on = _feature_on(analytics, "uniform")
    coverage_on = _feature_on(analytics, "coverage")
    poses = SimplePoseAnalyzer()
    actions = CompositeActionAnalyzer()
    frames = 0
    poses_found = 0
    events_sent = 0
    coverage_zones = 0
    # Флаг «нет спецодежды» эмитим однократно на задание (антиспам).
    uniform_flagged = False
    # heat-маска движения для расчёта покрытия зон (только если зоны заданы).
    heat: BoolMask | None = None
    prev_frame: Frame | None = None
    # Кадр-доказательство: первый кадр, породивший события (для скриншота).
    evidence_frame: Frame | None = None
    artifact_path: str | None = None
    try:
        for frame in source.frames():
            frames += 1
            if zones and coverage_on:
                heat = _accumulate_motion(heat, prev_frame, frame)
                prev_frame = frame
            pose = detector.detect(frame)
            if pose is None:
                continue
            poses_found += 1
            ts = now_fn()
            events_before = events_sent
            if pose_on:
                for detection in poses.process(pose):
                    sink.emit(build_pose_event(detection, task.room_id, ts))
                    events_sent += 1
            if actions_on:
                for action in actions.process(pose, ts):
                    sink.emit(build_action_event(action, task.room_id, ts))
                    events_sent += 1
            # Эвристика «белого халата»: при видимом торсе и отсутствии халата —
            # одно событие condition_flagged на задание.
            if (
                uniform_on
                and not uniform_flagged
                and all(pose.visible(lm) for lm in _TORSO_LANDMARKS)
            ):
                brightness, saturation = mean_brightness_saturation(frame, torso_polygon(pose))
                if not is_white_coat(brightness, saturation):
                    sink.emit(build_condition_flagged(brightness, saturation, task.room_id, ts))
                    events_sent += 1
                    uniform_flagged = True
            # Запомнить первый кадр, на котором появились события (для скриншота).
            if evidence_frame is None and events_sent > events_before:
                evidence_frame = frame
        # После прохода кадров — отчёт о покрытии каждой ROI-зоны (один на зону).
        if zones and coverage_on and heat is not None:
            ts = now_fn()
            for zone in zones:
                cov = zone_coverage_pct(heat, zone.polygon)
                event = build_coverage_event(zone.zone_type.value, zone.id, cov, task.room_id, ts)
                sink.emit(event)
                events_sent += 1
                coverage_zones += 1
        # Скриншот-доказательство: один артефакт на задание при наличии событий.
        if evidence_frame is not None and engine is not None:
            artifact_id = uuid4()
            ats = now_fn()
            artifact_path = build_artifact_path(artifacts_dir, ats, artifact_id, "jpg")
            save_frame(evidence_frame, artifact_path)
            insert_artifact(
                engine,
                Artifact(
                    id=artifact_id,
                    created_at=ats,
                    kind=ArtifactKind.SCREENSHOT,
                    path=artifact_path,
                    room_id=task.room_id,
                    camera_id=task.camera_id,
                    task_id=task.id,
                ),
            )
    finally:
        source.close()
    return {
        "frames": frames,
        "poses": poses_found,
        "events": events_sent,
        "coverage_zones": coverage_zones,
        "artifact": artifact_path,
    }


def run_once(
    engine: Engine,
    settings: Settings,
    *,
    detector: PoseDetector,
    sink: EventSink,
    source_factory: SourceFactory,
    save_frame: Callable[[Frame, str], None] = save_screenshot,
    now_fn: Callable[[], datetime] = _now_utc,
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
        # Тумблеры аналитики и ROI-зоны берём по камере задания.
        camera = load_camera(engine, task.camera_id) if task.camera_id else None
        analytics = _resolve_analytics(camera)
        zones = (
            load_camera_zones(engine, task.camera_id)
            if task.camera_id and _feature_on(analytics, "coverage")
            else []
        )
        result = process_task(
            task,
            source=source,
            detector=detector,
            sink=sink,
            zones=zones,
            analytics=analytics,
            engine=engine,
            artifacts_dir=settings.artifacts_dir,
            save_frame=save_frame,
            now_fn=now_fn,
        )
    except Exception as exc:
        logger.exception("Видеоаналитика: задание %s завершилось ошибкой", task.id)
        mark_failed(engine, task.id, now_fn(), str(exc))
        return True
    mark_done(engine, task.id, now_fn(), result)
    logger.info("Видеоаналитика: задание %s готово: %s", task.id, result)
    return True
