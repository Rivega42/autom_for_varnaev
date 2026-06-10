"""Доступ к показаниям датчиков (sensor_readings) из api-gateway."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select

from api_gateway.tables import sensor_readings


def _iso(value: datetime) -> str:
    """Привести время к ISO-8601 UTC (naive из SQLite считаем UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _reading_to_api(row: dict[str, Any]) -> dict[str, Any]:
    """Преобразовать строку sensor_readings в форму ответа API (room, ISO-время)."""
    return {
        "ts": _iso(row["ts"]),
        "node_id": row["node_id"],
        "room": row["room_id"],
        "metric": row["metric"],
        "value": row["value"],
        "unit": row["unit"],
    }


def list_readings(
    engine: Engine,
    room: str | None = None,
    metric: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Показания с фильтрами по помещению/метрике/времени (новые сверху)."""
    stmt = select(sensor_readings)
    if room is not None:
        stmt = stmt.where(sensor_readings.c.room_id == room)
    if metric is not None:
        stmt = stmt.where(sensor_readings.c.metric == metric)
    if from_ts is not None:
        stmt = stmt.where(sensor_readings.c.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(sensor_readings.c.ts < to_ts)
    stmt = stmt.order_by(sensor_readings.c.ts.desc()).limit(limit)

    with engine.connect() as conn:
        return [_reading_to_api(dict(r)) for r in conn.execute(stmt).mappings()]


def latest_readings(
    engine: Engine, scan_limit: int = 1000
) -> tuple[dict[str, datetime], dict[tuple[str | None, str], dict[str, Any]]]:
    """Свести последние показания: по узлу (ts) и по (помещение, метрика) (значение).

    Просматриваем последние `scan_limit` показаний (по убыванию ts) и берём первое
    встреченное для каждого ключа — оно и есть самое свежее. Узел/помещение, давно
    не присылавшие данные, в окно не попадают и считаются «молчащими» — это и нужно
    для индикации живости на обзорном экране (#288).
    """
    stmt = select(sensor_readings).order_by(sensor_readings.c.ts.desc()).limit(scan_limit)
    node_latest: dict[str, datetime] = {}
    room_metric: dict[tuple[str | None, str], dict[str, Any]] = {}
    with engine.connect() as conn:
        for r in conn.execute(stmt).mappings():
            node_id = r["node_id"]
            if node_id is not None and node_id not in node_latest:
                node_latest[node_id] = r["ts"]
            key = (r["room_id"], r["metric"])
            if key not in room_metric:
                room_metric[key] = {"value": r["value"], "unit": r["unit"], "ts": _iso(r["ts"])}
    return node_latest, room_metric
