"""Проверка расчёта % покрытия ROI-зон."""

from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from video_analytics.coverage import build_coverage_event, polygon_mask, zone_coverage_pct
from video_analytics.repository import load_camera_zones
from video_analytics.tables import camera_zones, metadata

from monitoring_shared import EventType

# Полигон — левая половина кадра.
_LEFT_HALF = [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]


def test_polygon_mask_area() -> None:
    mask = polygon_mask(10, 10, _LEFT_HALF)
    # левая половина ~50 пикселей из 100
    assert 40 <= int(mask.sum()) <= 60


def test_zone_coverage_full_and_partial() -> None:
    heat_full = np.ones((10, 10), dtype=np.bool_)
    assert zone_coverage_pct(heat_full, _LEFT_HALF) == 100.0

    heat_none = np.zeros((10, 10), dtype=np.bool_)
    assert zone_coverage_pct(heat_none, _LEFT_HALF) == 0.0


def test_load_camera_zones() -> None:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    cam_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            camera_zones.insert().values(
                id=1, camera_id=cam_id, zone_type="table", polygon=_LEFT_HALF, note=None
            )
        )
    zones = load_camera_zones(engine, cam_id)
    assert len(zones) == 1
    assert zones[0].zone_type.value == "table"


def test_build_coverage_event() -> None:
    event = build_coverage_event(
        "table", 7, 63.4, "room-01", datetime(2026, 6, 5, 10, 0, tzinfo=UTC)
    )
    assert event.type is EventType.COVERAGE_REPORT
    assert event.payload["coverage_pct"] == 63
