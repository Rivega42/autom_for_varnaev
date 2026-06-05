"""thresholds: пороги для метрик по помещениям (критерии событий датчиков).

Revision ID: 0008_thresholds
Revises: 0007_events
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_thresholds"
down_revision: str | None = "0007_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу порогов."""
    op.create_table(
        "thresholds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # NULL = глобальный порог (для всех помещений)
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column("metric", sa.Text(), nullable=False),
        # оператор сравнения: ">" | "<" | ">=" | "<="
        sa.Column("op", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        # важность срабатывания: "warning" | "critical"
        sa.Column("severity", sa.Text(), nullable=False),
        # порог "тишины" узла, мин (для события sensor_silent)
        sa.Column("silent_min", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Удалить таблицу порогов."""
    op.drop_table("thresholds")
