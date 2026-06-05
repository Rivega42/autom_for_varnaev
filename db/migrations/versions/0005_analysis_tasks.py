"""analysis_tasks: задания на видеоанализ (сущность первого класса уже в v1).

Revision ID: 0005_analysis_tasks
Revises: 0004_camera_zones
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_analysis_tasks"
down_revision: str | None = "0004_camera_zones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу заданий на анализ."""
    op.create_table(
        "analysis_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # источник: "stream" (RTSP/WebRTC) | "file" (путь на томе)
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column("pipeline", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        # статус жизненного цикла: queued|running|done|failed|cancelled
        sa.Column("status", sa.Text(), nullable=False),
        # источник триггера: "schedule" | "manual"; "aura" зарезервирован — СТЫК-АУРА (v2)
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # СТЫК-АУРА (v2): webhook о готовности задания; в v1 не используется
        sa.Column("callback_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Удалить таблицу заданий на анализ."""
    op.drop_table("analysis_tasks")
