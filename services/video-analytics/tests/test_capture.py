"""Проверка источника stream (без cv2 — фейковый VideoCapture)."""

import numpy as np
from video_analytics.capture import StreamFrameSource


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self._frames = list(frames)
        self.released = False

    def read(self) -> tuple[bool, object]:
        if self._frames:
            return True, self._frames.pop(0)
        return False, None

    def release(self) -> None:
        self.released = True


def _frame(value: int) -> np.ndarray:
    return np.full((2, 2, 3), value, dtype=np.uint8)


def test_stream_source_reads_until_end() -> None:
    cap = _FakeCapture([_frame(0), _frame(1), _frame(2)])
    source = StreamFrameSource("rtsp://cam-01/stream", capture_factory=lambda _ref: cap)
    frames = list(source.frames())
    assert len(frames) == 3
    source.close()
    assert cap.released is True
