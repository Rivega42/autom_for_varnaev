"""artifacts: файлы-доказательства (скриншоты/keypoints; в v2 — видео).

Revision ID: 0006_artifacts
Revises: 0005_analysis_tasks
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_artifacts"
down_revision: str | None = "0005_analysis_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу артефактов."""
    op.create_table(
        "artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # тип артефакта: "screenshot" | "keypoints" | "coverage" | "video"
        sa.Column("kind", sa.Text(), nullable=False),
        # путь на общем томе: /data/artifacts/<YYYY-MM-DD>/<id>.<ext>
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=True),
        sa.Column(
            "camera_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cameras.id"),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_tasks.id"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Удалить таблицу артефактов."""
    op.drop_table("artifacts")
