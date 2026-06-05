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
