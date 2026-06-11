"""Continuous aggregate + сжатие/retention сырых показаний (#295).

Почасовая свёртка sensor_readings_hourly (avg/min/max по помещению и метрике) —
для быстрых дашбордов на длинных рядах; политика её обновления; сжатие сырых
рядов (lossless) и retention сырья (по умолчанию выключен — значения по #41).

DDL TimescaleDB (continuous aggregate и add_*_policy) нельзя выполнять внутри
транзакции Alembic, поэтому он обёрнут в autocommit_block(). Прогон — только на
TimescaleDB (хост); в тестах проверяется структура файла (#295).

Параметры из окружения сервиса migrate:
  READINGS_COMPRESS_AFTER_DAYS — сжимать чанки старше N дней (по умолчанию 7);
  READINGS_RETENTION_DAYS      — удалять сырьё старше N дней (0 = выключено).

Revision ID: 0018_readings_rollup
Revises: 0017_audit_log
Create Date: 2026-06-11
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0018_readings_rollup"
down_revision: str | None = "0017_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Почасовая свёртка: avg/min/max по (помещение, метрика); unit — в группировке
# (для пары помещение+метрика он постоянный, поэтому не теряется).
_CREATE_CAGG = """
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_readings_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', ts) AS bucket,
       room_id,
       metric,
       unit,
       avg(value) AS avg_value,
       min(value) AS min_value,
       max(value) AS max_value
FROM sensor_readings
GROUP BY bucket, room_id, metric, unit
WITH NO DATA
"""

# Обновление свёртки: пересчитывать недавнее окно раз в час.
_ADD_REFRESH = """
SELECT add_continuous_aggregate_policy('sensor_readings_hourly',
    start_offset => INTERVAL '3 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour')
"""


def _compress_after_days() -> int:
    return int(os.getenv("READINGS_COMPRESS_AFTER_DAYS", "7"))


def _retention_days() -> int:
    return int(os.getenv("READINGS_RETENTION_DAYS", "0"))


def upgrade() -> None:
    """Создать свёртку и включить политики (вне транзакции Alembic)."""
    with op.get_context().autocommit_block():
        op.execute(_CREATE_CAGG)
        op.execute(_ADD_REFRESH)
        # Сжатие сырья (lossless): сегментируем по узлу и метрике.
        op.execute(
            "ALTER TABLE sensor_readings SET ("
            "timescaledb.compress, "
            "timescaledb.compress_segmentby = 'node_id, metric')"
        )
        op.execute(
            f"SELECT add_compression_policy('sensor_readings', "
            f"INTERVAL '{_compress_after_days()} days')"
        )
        # Retention сырья — только если задан положительный порог (#41).
        retention = _retention_days()
        if retention > 0:
            op.execute(
                f"SELECT add_retention_policy('sensor_readings', INTERVAL '{retention} days')"
            )


def downgrade() -> None:
    """Снять политики и удалить свёртку (вне транзакции Alembic)."""
    with op.get_context().autocommit_block():
        op.execute("SELECT remove_retention_policy('sensor_readings', if_exists => true)")
        op.execute("SELECT remove_compression_policy('sensor_readings', if_exists => true)")
        op.execute("ALTER TABLE sensor_readings SET (timescaledb.compress = false)")
        op.execute(
            "SELECT remove_continuous_aggregate_policy('sensor_readings_hourly', if_exists => true)"
        )
        op.execute("DROP MATERIALIZED VIEW IF EXISTS sensor_readings_hourly")
