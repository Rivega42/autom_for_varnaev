"""camera_zones: ROI-зоны камеры (стол/пол/окно) для % покрытия.

Revision ID: 0004_camera_zones
Revises: 0003_cameras
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_camera_zones"
down_revision: str | None = "0003_cameras"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать ROI-зоны камер."""
    op.create_table(
        "camera_zones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "camera_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cameras.id"),
            nullable=False,
        ),
        # тип зоны: "table" | "floor" | "window"
        sa.Column("zone_type", sa.Text(), nullable=False),
        # вершины ROI-полигона (нормированные координаты), JSON
        sa.Column("polygon", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Удалить ROI-зоны камер."""
    op.drop_table("camera_zones")
