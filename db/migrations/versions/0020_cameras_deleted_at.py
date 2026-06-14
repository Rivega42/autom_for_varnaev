"""cameras: мягкое удаление через deleted_at (#329).

Камера — точка привязки доказательной базы (analysis_tasks, artifacts, events).
Жёсткое удаление сломало бы FK или стёрло историю для ППК, поэтому удаление —
мягкое: deleted_at помечает камеру скрытой (исчезает из справочника/обзора),
история сохраняется. Параллельно камера выключается (enabled=false), чтобы
планировщик перестал её опрашивать.

Revision ID: 0020_cameras_deleted_at
Revises: 0019_presence_rules
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_cameras_deleted_at"
down_revision: str | None = "0019_presence_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить cameras.deleted_at (NULL = активна)."""
    op.add_column("cameras", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    """Убрать cameras.deleted_at."""
    op.drop_column("cameras", "deleted_at")
