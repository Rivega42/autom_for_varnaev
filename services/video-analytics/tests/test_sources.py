"""Проверка абстракции источника кадров и понижения fps."""

import numpy as np
from video_analytics.sources import (
    FakeFrameSource,
    ThrottledFrameSource,
    fps_step,
    select_every,
)


def _frame(value: int) -> np.ndarray:
    return np.full((2, 2, 3), value, dtype=np.uint8)


def test_fps_step() -> None:
    assert fps_step(25, 5) == 5
    assert fps_step(8, 5) == 2  # round(1.6)
    assert fps_step(5, 0) == 1


def test_select_every() -> None:
    frames = [_frame(i) for i in range(10)]
    picked = list(select_every(frames, 3))
    # индексы 0,3,6,9
    assert len(picked) == 4
    assert int(picked[1][0, 0, 0]) == 3


def test_throttled_source_and_close() -> None:
    inner = FakeFrameSource([_frame(i) for i in range(10)])
    throttled = ThrottledFrameSource(inner, src_fps=15, target_fps=5)  # step 3
    assert len(list(throttled.frames())) == 4
    throttled.close()
    assert inner.closed is True
