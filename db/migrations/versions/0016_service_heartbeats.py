"""service_heartbeats: живость наших сервисов (watchdog, #284).

Каждый ключевой сервис (ingest-sensors, scheduler, video-analytics) периодически
обновляет свою строку (UPSERT по service). Планировщик читает таблицу и, если
сервис «замолчал» дольше порога, эмитит событие service_silent; при возврате —
service_restored. Симметрично «тишине» узла датчика.

Revision ID: 0016_service_heartbeats
Revises: 0015_events_ack
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_service_heartbeats"
down_revision: str | None = "0015_events_ack"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу heartbeat'ов сервисов."""
    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.Text(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", sa.JSON()),
    )


def downgrade() -> None:
    """Убрать таблицу heartbeat'ов."""
    op.drop_table("service_heartbeats")
