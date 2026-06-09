"""Проверка источника file и фабрики источников."""

import numpy as np
from video_analytics.capture import FileFrameSource, create_frame_source

from monitoring_shared import SourceType


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


def test_file_source_reads() -> None:
    cap = _FakeCapture([_frame(0), _frame(1)])
    source = FileFrameSource("/data/clip.mp4", capture_factory=lambda _ref: cap)
    assert len(list(source.frames())) == 2
    source.close()
    assert cap.released is True


def test_factory_stream_and_file_with_throttle() -> None:
    frames = [_frame(i) for i in range(10)]

    def factory(_ref: str) -> _FakeCapture:
        return _FakeCapture(list(frames))

    stream = create_frame_source(
        SourceType.STREAM, "rtsp://x", capture_factory=factory, src_fps=15, target_fps=5
    )
    # step 3 → кадры 0,3,6,9
    assert len(list(stream.frames())) == 4

    file_src = create_frame_source(
        SourceType.FILE, "/data/clip.mp4", capture_factory=factory, src_fps=5, target_fps=5
    )
    assert len(list(file_src.frames())) == 10


def test_stream_limited_by_max_frames() -> None:
    """Для stream max_frames ограничивает число кадров (live-RTSP не бесконечен)."""
    frames = [_frame(i) for i in range(100)]

    def factory(_ref: str) -> _FakeCapture:
        return _FakeCapture(list(frames))

    stream = create_frame_source(
        SourceType.STREAM,
        "rtsp://x",
        capture_factory=factory,
        src_fps=5,
        target_fps=5,
        max_frames=7,
    )
    assert len(list(stream.frames())) == 7


def test_file_ignores_max_frames() -> None:
    """Для file лимит кадров не применяется (источник конечен сам по себе)."""
    frames = [_frame(i) for i in range(10)]

    def factory(_ref: str) -> _FakeCapture:
        return _FakeCapture(list(frames))

    file_src = create_frame_source(
        SourceType.FILE,
        "/data/clip.mp4",
        capture_factory=factory,
        src_fps=5,
        target_fps=5,
        max_frames=3,
    )
    assert len(list(file_src.frames())) == 10
