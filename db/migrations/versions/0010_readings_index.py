"""Индекс (room_id, metric, ts DESC) на sensor_readings под дашборды Grafana.

Revision ID: 0010_readings_index
Revises: 0009_sensor_readings
Create Date: 2026-06-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_readings_index"
down_revision: str | None = "0009_sensor_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_sensor_readings_room_metric_ts"


def upgrade() -> None:
    """Создать составной индекс под выборки последних показаний по помещению/метрике."""
    op.create_index(
        INDEX_NAME,
        "sensor_readings",
        ["room_id", "metric", sa.text("ts DESC")],
    )


def downgrade() -> None:
    """Удалить составной индекс."""
    op.drop_index(INDEX_NAME, table_name="sensor_readings")
