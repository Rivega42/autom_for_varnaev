"""cameras: справочник камер по помещениям.

Revision ID: 0003_cameras
Revises: 0002_sensor_nodes
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_cameras"
down_revision: str | None = "0002_sensor_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать справочник камер."""
    op.create_table(
        "cameras",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # источник потока для media-gateway
        sa.Column("rtsp_url", sa.Text(), nullable=False),
        # пресет ракурса из PoC (JSON)
        sa.Column("viewpoint", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Удалить справочник камер."""
    op.drop_table("cameras")
