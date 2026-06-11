"""Тесты контроля запретных зон (#299): точка человека, вход/выход, событие."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from video_analytics.landmarks import POSE_LANDMARK_COUNT, Landmark, PoseLandmark, PoseResult
from video_analytics.presence import (
    ZoneEntryMonitor,
    ZonePolygon,
    build_forbidden_zone_entry,
    build_presence_detected,
    forbidden_zones,
    person_point,
    work_zones,
)

from monitoring_shared import CameraZone, EventType, ZoneType

_T0 = datetime(2026, 6, 6, 10, 0, tzinfo=UTC)
# Квадрат в правом-нижнем углу кадра.
_ZONE = ZonePolygon(zone_id=1, polygon=[[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]])


def _pose(hip_x: float, hip_y: float, visible: float = 0.9) -> PoseResult:
    pts = [Landmark(0.0, 0.0, 0.0) for _ in range(POSE_LANDMARK_COUNT)]
    pts[int(PoseLandmark.LEFT_HIP)] = Landmark(hip_x, hip_y, visible)
    pts[int(PoseLandmark.RIGHT_HIP)] = Landmark(hip_x, hip_y, visible)
    return PoseResult(pts)


def test_person_point_uses_hips() -> None:
    """Точка человека — середина бёдер при их видимости."""
    assert person_point(_pose(0.6, 0.7)) == (0.6, 0.7)


def test_person_point_none_when_torso_invisible() -> None:
    """Без видимых бёдер/плеч точки нет."""
    assert person_point(_pose(0.6, 0.7, visible=0.1)) is None


def test_zone_type_filters() -> None:
    """Из зон камеры отбираются запретные и рабочие по типу."""
    cam = uuid4()
    zones = [
        CameraZone(id=1, camera_id=cam, zone_type=ZoneType.TABLE, polygon=[[0, 0]], note=None),
        CameraZone(id=2, camera_id=cam, zone_type=ZoneType.FORBIDDEN, polygon=[[0, 0]], note=None),
        CameraZone(id=3, camera_id=cam, zone_type=ZoneType.WORK, polygon=[[0, 0]], note=None),
    ]
    assert [z.zone_id for z in forbidden_zones(zones)] == [2]
    assert [z.zone_id for z in work_zones(zones)] == [3]


def test_monitor_fires_on_entry_once_then_resets() -> None:
    """Вход в зону — одно событие; пока внутри — тишина; выход и новый вход — снова."""
    mon = ZoneEntryMonitor([_ZONE])
    assert mon.update((0.1, 0.1)) == []  # снаружи
    assert mon.update((0.7, 0.7)) == [1]  # вошёл → эпизод
    assert mon.update((0.8, 0.8)) == []  # всё ещё внутри — повтора нет
    assert mon.update((0.1, 0.1)) == []  # вышел
    assert mon.update((0.7, 0.7)) == [1]  # снова вошёл → новый эпизод


def test_monitor_none_point_treated_as_outside() -> None:
    """Нет точки человека (торс не виден) — как «снаружи», сбрасывает эпизод."""
    mon = ZoneEntryMonitor([_ZONE])
    assert mon.update((0.7, 0.7)) == [1]
    assert mon.update(None) == []  # человека не видно
    assert mon.update((0.7, 0.7)) == [1]  # появился снова → новый эпизод


def test_build_presence_detected() -> None:
    ev = build_presence_detected(5, "room-01", _T0)
    assert ev.type is EventType.PRESENCE_DETECTED
    assert ev.severity.value == "info"
    assert ev.payload["zone_id"] == 5


def test_build_event() -> None:
    ev = build_forbidden_zone_entry(7, "room-01", _T0)
    assert ev.type is EventType.FORBIDDEN_ZONE_ENTRY
    assert ev.payload["zone_id"] == 7
    assert ev.room_id == "room-01"
