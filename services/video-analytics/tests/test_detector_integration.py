"""Опциональный интеграционный прогон реального MediaPipe (#206).

Выполняется только при наличии файла модели (models/pose_landmarker.task,
кладётся `bash scripts/fetch_model.sh`) и установленного mediapipe — то есть
локально на машине разработчика/объекте. В CI зависимости и модели нет — тест
корректно скипается, обычные тесты аналитики по-прежнему идут на фейках.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_MODEL = Path(__file__).resolve().parents[3] / "models" / "pose_landmarker.task"


@pytest.mark.skipif(not _MODEL.is_file(), reason="нет файла модели pose_landmarker.task")
def test_real_model_smoke() -> None:
    """Детектор поднимается на реальной модели и обрабатывает кадр без ошибок."""
    pytest.importorskip("mediapipe", reason="mediapipe не установлен (опциональный тест)")
    from video_analytics.detector import MediaPipePoseDetector

    detector = MediaPipePoseDetector(str(_MODEL))
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # На пустом кадре человека нет — важен сам факт штатного инференса.
    assert detector.detect(frame) is None
