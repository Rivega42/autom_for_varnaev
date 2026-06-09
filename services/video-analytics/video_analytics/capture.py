"""Источники кадров на базе OpenCV VideoCapture (stream/file).

OpenCV (cv2) — runtime-зависимость; фабрика захвата инъектируется, поэтому
логика чтения кадров тестируется без cv2.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Protocol

from monitoring_shared import SourceType
from video_analytics.sources import Frame, FrameSource, ThrottledFrameSource


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


class FileFrameSource:
    """Источник кадров `file`: чтение видеофайла с тома.

    # СТЫК-АУРА (v2): в v1 режим `file` дёргается только нашим планировщиком/
    # тестами; в v2 сюда приходит путь к файлу/фрагменту от АУРА.
    """

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


class LimitedFrameSource:
    """Отдаёт не больше `max_frames` кадров из обёрнутого источника.

    Нужен для live-потоков (RTSP бесконечен): без лимита `process_task` читал бы
    кадры вечно и не доходил до отчёта о покрытии. Для конечных источников (file)
    не применяется.
    """

    def __init__(self, inner: FrameSource, max_frames: int) -> None:
        self._inner = inner
        self._max_frames = max_frames

    def frames(self) -> Iterator[Frame]:
        for index, frame in enumerate(self._inner.frames()):
            if index >= self._max_frames:
                break
            yield frame

    def close(self) -> None:
        self._inner.close()


def create_frame_source(
    source_type: SourceType,
    source_ref: str,
    *,
    capture_factory: CaptureFactory | None = None,
    src_fps: float = 25.0,
    target_fps: int = 5,
    max_frames: int | None = None,
) -> FrameSource:
    """Создать источник кадров по типу задания (stream|file) с понижением fps.

    Для `stream` при заданном `max_frames` (> 0) поток ограничивается этим числом
    кадров — иначе анализ live-RTSP не завершается. Для `file` лимит игнорируется.
    """
    inner: FrameSource
    if source_type is SourceType.STREAM:
        inner = StreamFrameSource(source_ref, capture_factory)
    elif source_type is SourceType.FILE:
        inner = FileFrameSource(source_ref, capture_factory)
    else:
        raise ValueError(f"Неизвестный тип источника: {source_type}")
    throttled: FrameSource = ThrottledFrameSource(inner, src_fps, target_fps)
    if source_type is SourceType.STREAM and max_frames is not None and max_frames > 0:
        return LimitedFrameSource(throttled, max_frames)
    return throttled
