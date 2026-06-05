"""events: единый журнал событий (включая человекочитаемое поле message).

Revision ID: 0007_events
Revises: 0006_artifacts
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_events"
down_revision: str | None = "0006_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать единый журнал событий."""
    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # источник события: "sensors" | "analytics"
        sa.Column("source", sa.Text(), nullable=False),
        # тип события (threshold_exceeded, sensor_silent, pose_event, ...)
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=True),
        # важность: "info" | "warning" | "critical"
        sa.Column("severity", sa.Text(), nullable=False),
        # человекочитаемый текст для оператора (RU, с контекстом помещения)
        sa.Column("message", sa.Text(), nullable=False),
        # машинные детали события
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Удалить единый журнал событий."""
    op.drop_table("events")
