"""Абстракция источника кадров для видеоаналитики.

Источник кадров — параметр пайплайна (docs/07 §3): `stream` (через
media-gateway) или `file` (путь на томе). Здесь — общий интерфейс,
понижение fps и фейковый источник для тестов. Конкретные реализации
stream/file (на OpenCV) добавляются в E4.5/E4.6 (cv2 — runtime, не в CI).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

# Кадр — BGR-изображение (как отдаёт OpenCV).
Frame = NDArray[np.uint8]


class FrameSource(Protocol):
    """Источник кадров: итерируемая последовательность + закрытие."""

    def frames(self) -> Iterator[Frame]: ...

    def close(self) -> None: ...


def fps_step(src_fps: float, target_fps: int) -> int:
    """Шаг прореживания кадров для понижения частоты до target_fps (>=1)."""
    if target_fps <= 0:
        return 1
    return max(1, round(src_fps / target_fps))


def select_every(frames: Iterable[Frame], step: int) -> Iterator[Frame]:
    """Брать каждый step-й кадр (понижение fps)."""
    for index, frame in enumerate(frames):
        if index % step == 0:
            yield frame


class ThrottledFrameSource:
    """Обёртка над источником: понижает частоту кадров до target_fps."""

    def __init__(self, inner: FrameSource, src_fps: float, target_fps: int) -> None:
        self._inner = inner
        self._step = fps_step(src_fps, target_fps)

    def frames(self) -> Iterator[Frame]:
        return select_every(self._inner.frames(), self._step)

    def close(self) -> None:
        self._inner.close()


class FakeFrameSource:
    """Источник из заранее заданного списка кадров (для тестов)."""

    def __init__(self, frames: list[Frame]) -> None:
        self._frames = frames
        self.closed = False

    def frames(self) -> Iterator[Frame]:
        yield from self._frames

    def close(self) -> None:
        self.closed = True
