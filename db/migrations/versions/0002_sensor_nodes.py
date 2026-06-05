"""sensor_nodes: справочник узлов датчиков (контроллеров).

Revision ID: 0002_sensor_nodes
Revises: 0001_rooms
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sensor_nodes"
down_revision: str | None = "0001_rooms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать справочник узлов датчиков."""
    op.create_table(
        "sensor_nodes",
        # идентификатор узла, напр. "node-01"
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=False),
        # размещение: "снаружи камеры (радио)", "внутри (I2C)" и т.п.
        sa.Column("placement", sa.Text(), nullable=True),
        # питание: "mains" | "battery"
        sa.Column("power", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Удалить справочник узлов датчиков."""
    op.drop_table("sensor_nodes")
