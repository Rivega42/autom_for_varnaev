"""Контроль присутствия по зонам: вход репрезентативной точки человека в зону.

Точка человека — середина бёдер (если видны), иначе плеч. На каждом кадре
проверяется её вхождение в полигоны зон (point-in-polygon). Вход фиксируется
один раз на эпизод по зоне (сброс при выходе). Используется для запретных зон
(`forbidden_zone_entry`, #299) и рабочих зон (`presence_detected`, #302). Это
присутствие по позе, не трекинг конкретных людей.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from monitoring_shared import CameraZone, Event, EventSource, EventType, Severity, ZoneType
from video_analytics.coverage import point_in_polygon
from video_analytics.landmarks import PoseLandmark, PoseResult


def person_point(pose: PoseResult) -> tuple[float, float] | None:
    """Точка положения человека: середина бёдер, иначе плеч; иначе None."""
    for left, right in (
        (PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP),
        (PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER),
    ):
        if pose.visible(left) and pose.visible(right):
            lp, rp = pose.point(left), pose.point(right)
            return (lp.x + rp.x) / 2.0, (lp.y + rp.y) / 2.0
    return None


@dataclass(frozen=True)
class ZonePolygon:
    """Зона для проверки присутствия: id и нормированный полигон."""

    zone_id: int
    polygon: list[list[float]]


def zones_of_type(zones: Sequence[CameraZone], zone_type: ZoneType) -> list[ZonePolygon]:
    """Отобрать зоны заданного типа из списка зон камеры."""
    return [ZonePolygon(z.id, z.polygon) for z in zones if z.zone_type is zone_type]


def forbidden_zones(zones: Sequence[CameraZone]) -> list[ZonePolygon]:
    """Запретные зоны камеры (#299)."""
    return zones_of_type(zones, ZoneType.FORBIDDEN)


def work_zones(zones: Sequence[CameraZone]) -> list[ZonePolygon]:
    """Рабочие зоны камеры (#302)."""
    return zones_of_type(zones, ZoneType.WORK)


class ZoneEntryMonitor:
    """Фиксирует вход человека в зоны (раз на эпизод по зоне; сброс при выходе)."""

    def __init__(self, zones: Sequence[ZonePolygon]) -> None:
        self._zones = list(zones)
        self._inside: set[int] = set()  # зоны, где человек уже отмечен внутри

    def update(self, point: tuple[float, float] | None) -> list[int]:
        """Вернуть id зон, в которые человек ТОЛЬКО ЧТО вошёл (новый эпизод)."""
        entered: list[int] = []
        for zone in self._zones:
            now_inside = point is not None and point_in_polygon(point[0], point[1], zone.polygon)
            if now_inside and zone.zone_id not in self._inside:
                self._inside.add(zone.zone_id)
                entered.append(zone.zone_id)
            elif not now_inside:
                self._inside.discard(zone.zone_id)
        return entered


def build_forbidden_zone_entry(zone_id: int, room_id: str | None, ts: datetime) -> Event:
    """Событие «человек в запретной зоне» (+стоп-кадр, #299)."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.FORBIDDEN_ZONE_ENTRY,
        room_id=room_id,
        severity=Severity.WARNING,
        message="Человек в запретной зоне",
        payload={"zone_id": zone_id},
    )


def build_presence_detected(zone_id: int, room_id: str | None, ts: datetime) -> Event:
    """Событие «зафиксировано присутствие в рабочей зоне» (#302)."""
    return Event(
        id=uuid4(),
        ts=ts,
        source=EventSource.ANALYTICS,
        type=EventType.PRESENCE_DETECTED,
        room_id=room_id,
        severity=Severity.INFO,
        message="Зафиксировано присутствие в рабочей зоне",
        payload={"zone_id": zone_id},
    )
