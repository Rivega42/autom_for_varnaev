"""analysis_tasks.camera_id: связь задания с камерой (для ROI-зон и % покрытия).

Зоны камеры (camera_zones) читаются по camera_id; чтобы видеоаналитика могла
посчитать покрытие зон для задания, задание должно знать свою камеру.
Планировщик проставляет camera_id по конфигу объекта. Поле nullable: задания
без привязки к камере (или без зон) просто не считают покрытие.

Revision ID: 0011_analysis_tasks_camera_id
Revises: 0010_readings_index
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_analysis_tasks_camera_id"
down_revision: str | None = "0010_readings_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить колонку camera_id (FK на cameras) в analysis_tasks."""
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "camera_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cameras.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Удалить колонку camera_id из analysis_tasks."""
    op.drop_column("analysis_tasks", "camera_id")
