"""events: подтверждение (ack) и эскалация уведомлений (#264).

acknowledged_at — оператор подтвердил событие (POST /events/{id}/ack);
escalated_at / escalation_count — последний повтор уведомления и их число
(неподтверждённые критичные события повторяются — эскалация).

Revision ID: 0015_events_ack
Revises: 0014_cleaning_rules
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_events_ack"
down_revision: str | None = "0014_cleaning_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить поля подтверждения/эскалации в events."""
    op.add_column("events", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("events", sa.Column("escalated_at", sa.DateTime(timezone=True)))
    op.add_column(
        "events",
        sa.Column("escalation_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Убрать поля подтверждения/эскалации."""
    op.drop_column("events", "escalation_count")
    op.drop_column("events", "escalated_at")
    op.drop_column("events", "acknowledged_at")
