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

import numpy as np
from sqlalchemy import Engine

from monitoring_shared import AnalysisTask, CameraZone, SourceType
from video_analytics.actions import CompositeActionAnalyzer, build_action_event
from video_analytics.config import Settings
from video_analytics.coverage import BoolMask, build_coverage_event, zone_coverage_pct
from video_analytics.detector import PoseDetector
from video_analytics.event_sink import EventSink
from video_analytics.landmarks import PoseLandmark
from video_analytics.pose_events import SimplePoseAnalyzer, build_pose_event
from video_analytics.repository import (
    claim_next_task,
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

# Фабрика источника кадров по (тип, ссылка, целевой fps) — для подмены в тестах.
SourceFactory = Callable[[SourceType, str, int], FrameSource]


def _now_utc() -> datetime:
    """Текущее время в UTC (вынесено для подмены в тестах)."""
    return datetime.now(UTC)


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
    now_fn: Callable[[], datetime] = _now_utc,
) -> dict[str, Any]:
    """Прогнать кадры задания через детектор и анализаторы, отправить события.

    Если переданы ROI-зоны камеры (`zones`), по накопленной heat-маске движения
    считается % покрытия каждой зоны и эмитится `coverage_report` (один на зону).
    Возвращает сводку (frames/poses/events/coverage_zones) для
    `analysis_tasks.result`. Источник кадров закрывается в любом случае.
    """
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
    try:
        for frame in source.frames():
            frames += 1
            if zones:
                heat = _accumulate_motion(heat, prev_frame, frame)
                prev_frame = frame
            pose = detector.detect(frame)
            if pose is None:
                continue
            poses_found += 1
            ts = now_fn()
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
        # После прохода кадров — отчёт о покрытии каждой ROI-зоны (один на зону).
        if zones and heat is not None:
            ts = now_fn()
            for zone in zones:
                cov = zone_coverage_pct(heat, zone.polygon)
                event = build_coverage_event(zone.zone_type.value, zone.id, cov, task.room_id, ts)
                sink.emit(event)
                events_sent += 1
                coverage_zones += 1
    finally:
        source.close()
    return {
        "frames": frames,
        "poses": poses_found,
        "events": events_sent,
        "coverage_zones": coverage_zones,
    }


def run_once(
    engine: Engine,
    settings: Settings,
    *,
    detector: PoseDetector,
    sink: EventSink,
    source_factory: SourceFactory,
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
        # ROI-зоны берём по камере задания; без камеры покрытие не считаем.
        zones = load_camera_zones(engine, task.camera_id) if task.camera_id else []
        result = process_task(
            task, source=source, detector=detector, sink=sink, zones=zones, now_fn=now_fn
        )
    except Exception as exc:
        logger.exception("Видеоаналитика: задание %s завершилось ошибкой", task.id)
        mark_failed(engine, task.id, now_fn(), str(exc))
        return True
    mark_done(engine, task.id, now_fn(), result)
    logger.info("Видеоаналитика: задание %s готово: %s", task.id, result)
    return True
