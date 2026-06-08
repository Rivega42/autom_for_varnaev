"""Детектор позы: абстракция над MediaPipe PoseLandmarker (пайплайн pose_v1).

MediaPipe изолирован за протоколом PoseDetector — логика аналитики
тестируется на синтетических PoseResult без реального инференса. Реализация
MediaPipePoseDetector импортирует mediapipe лениво (runtime-зависимость, не в CI).
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from video_analytics.landmarks import Landmark, PoseResult
from video_analytics.sources import Frame

# Имя пайплайна (значение analysis_tasks.pipeline).
PIPELINE = "pose_v1"


class PoseDetector(Protocol):
    """Детектор позы: кадр → PoseResult (или None, если человек не найден)."""

    def detect(self, frame: Frame) -> PoseResult | None: ...


class MediaPipePoseDetector:
    """Реализация на MediaPipe Tasks `PoseLandmarker` (lazy-import mediapipe)."""

    def __init__(self, model_path: str) -> None:
        # Ленивая загрузка тяжёлой зависимости — не нужна в CI/тестах.
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        base = mp_python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(base_options=base, num_poses=1)
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def detect(self, frame: Frame) -> PoseResult | None:
        """Прогнать кадр через PoseLandmarker.

        OpenCV отдаёт кадр в BGR, а MediaPipe ожидает RGB — конвертируем порядок
        каналов (иначе цветозависимые эвристики и инференс работают по искажённым
        цветам). `ascontiguousarray` нужен MediaPipe (C-непрерывный буфер).
        """
        import mediapipe as mp

        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result: Any = self._landmarker.detect(image)
        if not result.pose_landmarks:
            return None
        points = result.pose_landmarks[0]
        return PoseResult([Landmark(p.x, p.y, p.visibility) for p in points])
