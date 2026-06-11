"""presence_rules: контроль присутствия в рабочей зоне по окну времени (#300).

В помещении в заданное окно (window_start–window_end, дневное) должно
фиксироваться присутствие персонала (события presence_detected от рабочих зон,
#302) не реже, чем раз в max_absence_min минут. Нарушение — событие
presence_missing (раз на эпизод). Времена окна — в часовом поясе PRESENCE_TZ
планировщика (по умолчанию UTC).

Revision ID: 0019_presence_rules
Revises: 0018_readings_rollup
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_presence_rules"
down_revision: str | None = "0018_readings_rollup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу правил контроля присутствия."""
    op.create_table(
        "presence_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=False),
        # Дневное окно (start < end); окна через полночь в v1 не поддерживаются.
        sa.Column("window_start", sa.Time(), nullable=False),
        sa.Column("window_end", sa.Time(), nullable=False),
        # Максимально допустимый перерыв присутствия внутри окна, минут.
        sa.Column("max_absence_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # На помещение может быть несколько окон (смены), но не дубли одного окна.
        sa.UniqueConstraint(
            "room_id", "window_start", "window_end", name="uq_presence_rules_room_window"
        ),
    )


def downgrade() -> None:
    """Удалить таблицу правил контроля присутствия."""
    op.drop_table("presence_rules")
