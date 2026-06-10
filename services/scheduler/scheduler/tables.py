"""Core-описание analysis_tasks для вставки заданий (диалект-нейтральное)."""

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


cleaning_rules = sa.Table(
    "cleaning_rules",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("room_id", sa.Text, nullable=False),
    sa.Column("zone_type", sa.Text, nullable=False),
    sa.Column("interval_hours", sa.Float, nullable=False),
    sa.Column("min_coverage_pct", sa.Integer, nullable=False),
    sa.Column("zone_name", sa.Text),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.UniqueConstraint("room_id", "zone_type", name="uq_cleaning_rules_room_zone"),
)


# Журнал событий: планировщик ЧИТАЕТ из него последние уборки (coverage_report).
events = sa.Table(
    "events",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("room_id", sa.Text),
    sa.Column("payload", sa.JSON),
)


# Справочники (планировщик ЧИТАЕТ): помещения и камеры — для проверки живости.
rooms = sa.Table(
    "rooms",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
)


cameras = sa.Table(
    "cameras",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("room_id", sa.Text),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False),
)


schedules = sa.Table(
    "schedules",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("source_ref", sa.Text, nullable=False),
    sa.Column("room_id", sa.Text),
    sa.Column("camera_id", sa.Uuid),
    sa.Column("pipeline", sa.Text, nullable=False),
    sa.Column("params", sa.JSON),
    sa.Column("interval_min", sa.Integer, nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.UniqueConstraint("name", name="uq_schedules_name"),
)
