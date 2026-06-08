"""cameras.analytics: пофункциональные тумблеры видеоаналитики на камеру.

JSONB-флаги включения функций аналитики для камеры: pose / actions / uniform /
coverage. NULL или отсутствие ключа = функция включена (обратная совместимость).
Управляются через REST (PATCH /api/v1/cameras/{id}); учитываются воркером.

Revision ID: 0012_cameras_analytics
Revises: 0011_analysis_tasks_camera_id
Create Date: 2026-06-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_cameras_analytics"
down_revision: str | None = "0011_analysis_tasks_camera_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить колонку analytics (JSONB) в cameras."""
    op.add_column("cameras", sa.Column("analytics", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Удалить колонку analytics из cameras."""
    op.drop_column("cameras", "analytics")
