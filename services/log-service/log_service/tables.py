"""Описание таблицы events для запросов log-service (SQLAlchemy Core).

Это не миграция (схему создаёт Alembic, E1) — отдельное Core-описание для
чтения/записи, переносимое между PostgreSQL и SQLite (для тестов). Типы
выбраны диалект-нейтральными: sa.Uuid, sa.JSON.
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

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
    sa.Column("task_id", sa.Uuid),
)
