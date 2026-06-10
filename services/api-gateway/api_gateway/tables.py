"""Core-описание таблиц для чтения/записи из api-gateway (диалект-нейтральное)."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

rooms = sa.Table(
    "rooms",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("is_cold", sa.Boolean, nullable=False),
)


sensor_nodes = sa.Table(
    "sensor_nodes",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("room_id", sa.Text, sa.ForeignKey("rooms.id"), nullable=False),
    sa.Column("placement", sa.Text),
    sa.Column("power", sa.Text),
    sa.Column("note", sa.Text),
)


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


thresholds = sa.Table(
    "thresholds",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("room_id", sa.Text),  # NULL = глобальный порог
    sa.Column("metric", sa.Text, nullable=False),
    sa.Column("op", sa.Text, nullable=False),
    sa.Column("value", sa.Float, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("silent_min", sa.Integer),
    sa.Column("enabled", sa.Boolean, nullable=False),
)


# Журнал событий: gateway ЧИТАЕТ его напрямую для отчётов (агрегаты по периоду,
# как Grafana) — REST log-service для постраничной ленты, не для агрегатов.
events = sa.Table(
    "events",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("room_id", sa.Text),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("message", sa.Text, nullable=False),
    sa.Column("payload", sa.JSON, nullable=False),
    sa.Column("artifact_id", sa.Uuid),
)


cleaning_rules = sa.Table(
    "cleaning_rules",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("room_id", sa.Text, sa.ForeignKey("rooms.id"), nullable=False),
    sa.Column("zone_type", sa.Text, nullable=False),
    sa.Column("interval_hours", sa.Float, nullable=False),
    sa.Column("min_coverage_pct", sa.Integer, nullable=False),
    sa.Column("zone_name", sa.Text),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.UniqueConstraint("room_id", "zone_type", name="uq_cleaning_rules_room_zone"),
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


schedules = sa.Table(
    "schedules",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    # Имя — уникальный ключ слота: планировщик склеивает БД и файл по имени.
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
