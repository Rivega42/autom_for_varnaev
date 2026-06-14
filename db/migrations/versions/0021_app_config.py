"""app_config: ключ-значение настроек контура (лицензия из GUI, #335).

Лицензионный ключ можно задать переменной LICENSE_KEY, но оператору удобнее
вставить его в GUI. Храним такие правки в app_config (ключ→значение); приоритет
у записи в БД, иначе берётся env. Таблица универсальна для будущих
GUI-настраиваемых параметров.

Revision ID: 0021_app_config
Revises: 0020_cameras_deleted_at
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_app_config"
down_revision: str | None = "0020_cameras_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу app_config (ключ-значение)."""
    op.create_table(
        "app_config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Удалить таблицу app_config."""
    op.drop_table("app_config")
