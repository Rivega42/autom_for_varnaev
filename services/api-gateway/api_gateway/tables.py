"""Core-описание таблиц для чтения/записи из api-gateway (диалект-нейтральное)."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

analysis_tasks = sa.Table(
    "analysis_tasks",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("source_ref", sa.Text, nullable=False),
    sa.Column("room_id", sa.Text),
    sa.Column("pipeline", sa.Text, nullable=False),
    sa.Column("params", sa.JSON),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("trigger", sa.Text, nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("result", sa.JSON),
    sa.Column("error", sa.Text),
    sa.Column("callback_url", sa.Text),
)


sensor_readings = sa.Table(
    "sensor_readings",
    metadata,
    sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    sa.Column("node_id", sa.Text),
    sa.Column("room_id", sa.Text),
    sa.Column("metric", sa.Text, nullable=False),
    sa.Column("value", sa.Float, nullable=False),
    sa.Column("unit", sa.Text, nullable=False),
)


cameras = sa.Table(
    "cameras",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("room_id", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("rtsp_url", sa.Text, nullable=False),
    sa.Column("viewpoint", sa.JSON),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.Column("analytics", sa.JSON),
)


camera_zones = sa.Table(
    "camera_zones",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("camera_id", sa.Uuid, nullable=False),
    sa.Column("zone_type", sa.Text, nullable=False),
    sa.Column("polygon", sa.JSON, nullable=False),
    sa.Column("note", sa.Text),
)
