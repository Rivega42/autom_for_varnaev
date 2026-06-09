"""Простые события поз (порт PoC §2.1): пороги с гистерезисом и антидребезгом.

Детекторы считают скалярную величину по ландмаркам; флаг с гистерезисом
(разные пороги входа/выхода) и антидребезгом (N кадров) даёт фронты. На
переднем фронте формируется событие pose_event.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto
from uuid import uuid4

from monitoring_shared import Event, EventSource, EventType, Severity
from video_analytics.landmarks import PoseLandmark, PoseResult


class Edge(StrEnum):
    """Фронт изменения состояния флага."""

    RISING = auto()
    FALLING = auto()


class HysteresisFlag:
    """Булев флаг с гистерезисом (enter/exit) и антидребезгом (debounce кадров)."""

    def __init__(self, enter: float, exit_: float, debounce: int = 2) -> None:
        self.active = False
        self._enter = enter
        self._exit = exit_
        self._debounce = debounce
        self._count = 0

    def update(self, value: float) -> Edge | None:
        """Обновить флаг значением; вернуть фронт (RISING/FALLING) или None."""
        target = value >= self._enter if not self.active else value > self._exit
        if target != self.active:
            self._count += 1
            if self._count >= self._debounce:
                self.active = target
                self._count = 0
                return Edge.RISING if target else Edge.FALLING
        else:
            self._count = 0
        return None


@dataclass(frozen=True)
class PoseSpec:
    """Описание простой позы (порт PoC §2.1).

    `value` — скалярная величина по ландмаркам (≥ enter → поза «принята»).
    `message` — передний фронт; `message_down` (опц.) — задний фронт (поза снята/
    нейтраль), эмитится со своим именем `pose_down`. `enter`/`exit_` (опц.) —
    пороги гистерезиса для этой позы (иначе общие из анализатора).
    """

    pose: str
    limb: str | None
    message: str
    required: tuple[PoseLandmark, ...]
    value: Callable[[PoseResult], float]
    message_down: str | None = None
    pose_down: str | None = None
    enter: float | None = None
    exit_: float | None = None


def _mid_x(p: PoseResult, a: PoseLandmark, b: PoseLandmark) -> float:
    """Середина по X между точками a и b."""
    return (p.point(a).x + p.point(b).x) / 2.0


def _mid_y(p: PoseResult, a: PoseLandmark, b: PoseLandmark) -> float:
    """Середина по Y между точками a и b."""
    return (p.point(a).y + p.point(b).y) / 2.0


def _squat_value(p: PoseResult) -> float:
    """Эвристика приседания: отношение бедро/торс уменьшается при приседе.

    value > 0 — присед. Нормировано на высоту торса (масштабонезависимо). При
    «нулевом» торсе (точки совпали) возвращаем неактив. Пороги подбираются под
    камеру — это перенос эвристики PoC, не точная биомеханика.
    """
    shoulder_y = _mid_y(p, PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER)
    hip_y = _mid_y(p, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
    knee_y = _mid_y(p, PoseLandmark.LEFT_KNEE, PoseLandmark.RIGHT_KNEE)
    torso = hip_y - shoulder_y
    if torso <= 0.02:
        return -1.0
    ratio = (knee_y - hip_y) / torso
    # Стоя ratio ~1; на приседе бедро «сжимается» → ratio падает.
    return 0.55 - ratio


# y растёт вниз: «выше» = меньшая y. Координаты нормированы [0..1].
_ARM_R = (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_WRIST)
_ARM_L = (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_WRIST)
_SHOULDERS = (PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER)
_HIPS = (PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)

_POSES: tuple[PoseSpec, ...] = (
    PoseSpec(
        "right_arm_up",
        "right_arm",
        "Поднята правая рука",
        _ARM_R,
        lambda p: p.point(PoseLandmark.RIGHT_SHOULDER).y - p.point(PoseLandmark.RIGHT_WRIST).y,
        message_down="Опущена правая рука",
        pose_down="right_arm_down",
    ),
    PoseSpec(
        "left_arm_up",
        "left_arm",
        "Поднята левая рука",
        _ARM_L,
        lambda p: p.point(PoseLandmark.LEFT_SHOULDER).y - p.point(PoseLandmark.LEFT_WRIST).y,
        message_down="Опущена левая рука",
        pose_down="left_arm_down",
    ),
    PoseSpec(
        "both_arms_up",
        "both_arms",
        "Подняты обе руки",
        (*_ARM_R, *_ARM_L),
        lambda p: min(
            p.point(PoseLandmark.RIGHT_SHOULDER).y - p.point(PoseLandmark.RIGHT_WRIST).y,
            p.point(PoseLandmark.LEFT_SHOULDER).y - p.point(PoseLandmark.LEFT_WRIST).y,
        ),
        message_down="Опущены обе руки",
        pose_down="both_arms_down",
    ),
    PoseSpec(
        "right_knee_up",
        "right_knee",
        "Поднято правое колено",
        (PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE),
        lambda p: p.point(PoseLandmark.RIGHT_HIP).y - p.point(PoseLandmark.RIGHT_KNEE).y,
        message_down="Опущено правое колено",
        pose_down="right_knee_down",
    ),
    PoseSpec(
        "left_knee_up",
        "left_knee",
        "Поднято левое колено",
        (PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE),
        lambda p: p.point(PoseLandmark.LEFT_HIP).y - p.point(PoseLandmark.LEFT_KNEE).y,
        message_down="Опущено левое колено",
        pose_down="left_knee_down",
    ),
    PoseSpec(
        "head_turn_right",
        None,
        "Голова повёрнута вправо",
        (PoseLandmark.NOSE, *_SHOULDERS),
        lambda p: p.point(PoseLandmark.NOSE).x - _mid_x(p, *_SHOULDERS),
        message_down="Голова прямо",
        pose_down="head_straight",
        enter=0.04,
    ),
    PoseSpec(
        "head_turn_left",
        None,
        "Голова повёрнута влево",
        (PoseLandmark.NOSE, *_SHOULDERS),
        lambda p: _mid_x(p, *_SHOULDERS) - p.point(PoseLandmark.NOSE).x,
        message_down="Голова прямо",
        pose_down="head_straight",
        enter=0.04,
    ),
    PoseSpec(
        "torso_lean_right",
        "torso",
        "Наклон корпуса вправо",
        (*_SHOULDERS, *_HIPS),
        lambda p: _mid_x(p, *_SHOULDERS) - _mid_x(p, *_HIPS),
        message_down="Корпус прямо",
        pose_down="torso_straight",
        enter=0.04,
    ),
    PoseSpec(
        "torso_lean_left",
        "torso",
        "Наклон корпуса влево",
        (*_SHOULDERS, *_HIPS),
        lambda p: _mid_x(p, *_HIPS) - _mid_x(p, *_SHOULDERS),
        message_down="Корпус прямо",
        pose_down="torso_straight",
        enter=0.04,
    ),
    PoseSpec(
        "squat",
        "torso",
        "Приседание",
        (*_SHOULDERS, *_HIPS, PoseLandmark.LEFT_KNEE, PoseLandmark.RIGHT_KNEE),
        _squat_value,
        message_down="Подъём из приседа",
        pose_down="stand_up",
        enter=0.08,
    ),
)


@dataclass(frozen=True)
class PoseDetection:
    """Распознанная простая поза (фронт смены состояния)."""

    pose: str
    limb: str | None
    message: str


class SimplePoseAnalyzer:
    """Отслеживает простые позы по кадрам с гистерезисом/антидребезгом.

    На переднем фронте эмитит `message`, на заднем (если задан `message_down`) —
    `message_down` с именем `pose_down` (напр. «опущена рука», «голова прямо»).
    """

    def __init__(self, enter: float = 0.05, exit_: float = 0.0, debounce: int = 2) -> None:
        self._flags = {
            spec.pose: HysteresisFlag(
                spec.enter if spec.enter is not None else enter,
                spec.exit_ if spec.exit_ is not None else exit_,
                debounce,
            )
            for spec in _POSES
        }

    def process(self, pose: PoseResult) -> list[PoseDetection]:
        """Обработать кадр; вернуть события поз на фронтах смены состояния."""
        detections: list[PoseDetection] = []
        for spec in _POSES:
            if not all(pose.visible(lm) for lm in spec.required):
                continue
            edge = self._flags[spec.pose].update(spec.value(pose))
            if edge is Edge.RISING:
                detections.append(PoseDetection(spec.pose, spec.limb, spec.message))
            elif edge is Edge.FALLING and spec.message_down is not None:
                detections.append(
                    PoseDetection(spec.pose_down or spec.pose, spec.limb, spec.message_down)
                )
        return detections


def build_pose_event(detection: PoseDetection, room_id: str | None, ts: datetime) -> Event:
    """Сформировать событие pose_event из распознанной позы."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.POSE_EVENT,
        room_id=room_id,
        severity=Severity.INFO,
        message=detection.message,
        payload={"pose": detection.pose, "limb": detection.limb},
    )
