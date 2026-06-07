"""Core-описание analysis_tasks для чтения/обновления (диалект-нейтральное)."""

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
    sa.Column("camera_id", sa.Uuid),
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
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("camera_id", sa.Uuid, nullable=False),
    sa.Column("zone_type", sa.Text, nullable=False),
    sa.Column("polygon", sa.JSON, nullable=False),
    sa.Column("note", sa.Text),
)


artifacts = sa.Table(
    "artifacts",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("path", sa.Text, nullable=False),
    sa.Column("mime", sa.Text),
    sa.Column("room_id", sa.Text),
    sa.Column("camera_id", sa.Uuid),
    sa.Column("task_id", sa.Uuid),
    sa.Column("meta", sa.JSON),
)
