"""rooms: справочник помещений объекта.

Revision ID: 0001_rooms
Revises:
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_rooms"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать справочник помещений."""
    op.create_table(
        "rooms",
        # человекочитаемый идентификатор помещения, напр. "room-01"
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        # признак холодильной/морозильной камеры (важно для холодовой цепи)
        sa.Column("is_cold", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Удалить справочник помещений."""
    op.drop_table("rooms")
