"""Источники кадров на базе OpenCV VideoCapture (stream/file).

OpenCV (cv2) — runtime-зависимость; фабрика захвата инъектируется, поэтому
логика чтения кадров тестируется без cv2.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Protocol

from video_analytics.sources import Frame


class VideoCapture(Protocol):
    """Минимальный интерфейс OpenCV VideoCapture."""

    def read(self) -> tuple[bool, Any]: ...

    def release(self) -> None: ...


CaptureFactory = Callable[[str], VideoCapture]


def cv2_capture(source_ref: str) -> VideoCapture:
    """Открыть источник через OpenCV (RTSP/WebRTC-релей media-gateway или файл)."""
    import cv2

    capture: VideoCapture = cv2.VideoCapture(source_ref)
    return capture


class StreamFrameSource:
    """Источник кадров `stream`: поток от media-gateway (RTSP/WebRTC)."""

    def __init__(self, source_ref: str, capture_factory: CaptureFactory | None = None) -> None:
        self._source_ref = source_ref
        self._factory = capture_factory or cv2_capture
        self._capture: VideoCapture | None = None

    def frames(self) -> Iterator[Frame]:
        self._capture = self._factory(self._source_ref)
        while True:
            ok, frame = self._capture.read()
            if not ok:
                break
            yield frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
