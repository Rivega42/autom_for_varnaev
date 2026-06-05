"""sensor_readings: временной ряд показаний датчиков (hypertable).

Revision ID: 0009_sensor_readings
Revises: 0008_thresholds
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_sensor_readings"
down_revision: str | None = "0008_thresholds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу показаний и превратить её в hypertable TimescaleDB."""
    op.create_table(
        "sensor_readings",
        # момент измерения (UTC) — колонка партиционирования hypertable
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("node_id", sa.Text(), sa.ForeignKey("sensor_nodes.id"), nullable=False),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id"), nullable=False),
        # метрика: "air_temp" | "humidity" | "surface_ir"
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        # единица: "C" | "%"
        sa.Column("unit", sa.Text(), nullable=False),
    )
    # Превращаем обычную таблицу в hypertable (требует расширения timescaledb, E1.2)
    op.execute("SELECT create_hypertable('sensor_readings', 'ts')")


def downgrade() -> None:
    """Удалить таблицу показаний (вместе с hypertable)."""
    op.drop_table("sensor_readings")
