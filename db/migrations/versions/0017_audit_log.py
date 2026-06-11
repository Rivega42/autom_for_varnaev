"""audit_log: аудит значимых действий настройки (#292).

Кто (роль исполнителя), что (метод+ресурс), когда, детали. Пишется api-gateway
на изменяющих эндпойнтах (создание/изменение/удаление справочников, камер, зон,
порогов, расписаний, правил; подтверждение событий ack). Читается через
GET /api/v1/audit (только admin).

Revision ID: 0017_audit_log
Revises: 0016_service_heartbeats
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_audit_log"
down_revision: str | None = "0016_service_heartbeats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу аудита действий."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),  # метка исполнителя (роль в v1)
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),  # HTTP-метод
        sa.Column("target", sa.Text(), nullable=False),  # путь ресурса
        sa.Column("detail", sa.JSON()),
    )


def downgrade() -> None:
    """Убрать таблицу аудита."""
    op.drop_table("audit_log")
