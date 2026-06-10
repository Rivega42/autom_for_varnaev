"""cleaning_rules: правила санитарного контроля уборки зон (#265).

Зона (помещение + тип) должна убираться не реже interval_hours; покрытие
последней уборки — не ниже min_coverage_pct. Нарушение — событие cleaning_overdue.

Revision ID: 0014_cleaning_rules
Revises: 0013_schedules
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_cleaning_rules"
down_revision: str | None = "0013_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу правил контроля уборки."""
    op.create_table(
        "cleaning_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=False),
        # Тип зоны как в camera_zones: table | floor | window.
        sa.Column("zone_type", sa.Text(), nullable=False),
        sa.Column("interval_hours", sa.Float(), nullable=False),
        sa.Column("min_coverage_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zone_name", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Одно правило на зону (помещение+тип).
        sa.UniqueConstraint("room_id", "zone_type", name="uq_cleaning_rules_room_zone"),
    )


def downgrade() -> None:
    """Удалить таблицу правил контроля уборки."""
    op.drop_table("cleaning_rules")
