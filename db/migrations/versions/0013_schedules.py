"""schedules: расписания видеоанализа (таймер), настраиваются через интерфейс.

Revision ID: 0013_schedules
Revises: 0012_cameras_analytics
Create Date: 2026-06-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_schedules"
down_revision: str | None = "0012_cameras_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу расписаний планировщика."""
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column(
            "camera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=True
        ),
        sa.Column("pipeline", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("interval_min", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Имя — уникальный ключ слота расписания (дедуп БД+файл идёт по имени).
        sa.UniqueConstraint("name", name="uq_schedules_name"),
    )


def downgrade() -> None:
    """Удалить таблицу расписаний."""
    op.drop_table("schedules")
