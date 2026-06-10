"""Сменный/суточный отчёт для санинспекции/ППК (#266): агрегаты за период.

Три раздела:
- уборки: события coverage_report (зона, время, %, ссылка на стоп-кадр);
- просрочки: события cleaning_overdue;
- холодовая цепь: по холодильным помещениям (rooms.is_cold) — мин/макс/среднее
  температуры воздуха за период и суммарное время вне нормы (по парам событий
  threshold_exceeded → back_to_normal).

Ограничение v1 (честно): «время вне нормы» считается по событиям ВНУТРИ периода;
превышение, начавшееся до периода, не видно (нет события в выборке). Незакрытое
к концу периода превышение считается до конца периода.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, func, select

from api_gateway.tables import events, rooms, sensor_readings

_API_PREFIX = "/api/v1"


def _as_utc(dt: datetime) -> datetime:
    """Naive время трактуем как UTC (SQLite в тестах возвращает naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def cleaning_section(engine: Engine, from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    """Уборки за период: из coverage_report (время, помещение, зона, %)."""
    stmt = (
        select(events.c.ts, events.c.room_id, events.c.message, events.c.payload)
        .where(events.c.type == "coverage_report", events.c.ts >= from_ts, events.c.ts < to_ts)
        .order_by(events.c.ts)
    )
    items: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for ts, room_id, message, payload in conn.execute(stmt):
            p = payload if isinstance(payload, dict) else {}
            items.append(
                {
                    "ts": _as_utc(ts).isoformat(),
                    "room": room_id,
                    "zone": p.get("zone"),
                    "coverage_pct": p.get("coverage_pct"),
                    "message": message,
                }
            )
    return items


def overdue_section(engine: Engine, from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    """Просрочки уборки за период (cleaning_overdue)."""
    stmt = (
        select(events.c.ts, events.c.room_id, events.c.message, events.c.payload)
        .where(events.c.type == "cleaning_overdue", events.c.ts >= from_ts, events.c.ts < to_ts)
        .order_by(events.c.ts)
    )
    items: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for ts, room_id, message, payload in conn.execute(stmt):
            p = payload if isinstance(payload, dict) else {}
            items.append(
                {
                    "ts": _as_utc(ts).isoformat(),
                    "room": room_id,
                    "zone": p.get("zone"),
                    "message": message,
                }
            )
    return items


def _out_of_range_minutes(
    engine: Engine, room_id: str, from_ts: datetime, to_ts: datetime
) -> float:
    """Суммарное время вне нормы (мин) по парам threshold_exceeded/back_to_normal."""
    stmt = (
        select(events.c.ts, events.c.type, events.c.payload)
        .where(
            events.c.room_id == room_id,
            events.c.type.in_(("threshold_exceeded", "back_to_normal")),
            events.c.ts >= from_ts,
            events.c.ts < to_ts,
        )
        .order_by(events.c.ts)
    )
    total_s = 0.0
    open_since: dict[str, datetime] = {}  # metric -> начало превышения
    with engine.connect() as conn:
        for ts, type_, payload in conn.execute(stmt):
            p = payload if isinstance(payload, dict) else {}
            metric = str(p.get("metric") or "")
            ts = _as_utc(ts)
            if type_ == "threshold_exceeded":
                open_since.setdefault(metric, ts)
            else:  # back_to_normal закрывает превышение по метрике
                start = open_since.pop(metric, None)
                if start is not None:
                    total_s += (ts - start).total_seconds()
    # незакрытые превышения — до конца периода
    for start in open_since.values():
        total_s += (_as_utc(to_ts) - start).total_seconds()
    return round(total_s / 60.0, 1)


def cold_chain_section(engine: Engine, from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    """Холодовая цепь: по каждому холодильному помещению — статистика воздуха."""
    with engine.connect() as conn:
        cold_rooms = [
            (r.id, r.name)
            for r in conn.execute(select(rooms.c.id, rooms.c.name).where(rooms.c.is_cold.is_(True)))
        ]
        items: list[dict[str, Any]] = []
        for room_id, name in cold_rooms:
            stats = conn.execute(
                select(
                    func.min(sensor_readings.c.value),
                    func.max(sensor_readings.c.value),
                    func.avg(sensor_readings.c.value),
                    func.count(),
                ).where(
                    sensor_readings.c.room_id == room_id,
                    sensor_readings.c.metric == "air_temp",
                    sensor_readings.c.ts >= from_ts,
                    sensor_readings.c.ts < to_ts,
                )
            ).one()
            items.append(
                {
                    "room": room_id,
                    "name": name,
                    "t_min": round(stats[0], 2) if stats[0] is not None else None,
                    "t_max": round(stats[1], 2) if stats[1] is not None else None,
                    "t_avg": round(stats[2], 2) if stats[2] is not None else None,
                    "readings": int(stats[3]),
                    "out_of_range_min": _out_of_range_minutes(engine, room_id, from_ts, to_ts),
                }
            )
    return items


def build_report(engine: Engine, from_ts: datetime, to_ts: datetime) -> dict[str, Any]:
    """Собрать отчёт за период (JSON-структура)."""
    return {
        "from": _as_utc(from_ts).isoformat(),
        "to": _as_utc(to_ts).isoformat(),
        "cleanings": cleaning_section(engine, from_ts, to_ts),
        "cleaning_overdue": overdue_section(engine, from_ts, to_ts),
        "cold_chain": cold_chain_section(engine, from_ts, to_ts),
    }


def report_to_csv(report: dict[str, Any]) -> str:
    """Отчёт в CSV (разделы с заголовками; UTF-8, ; как разделитель для Excel)."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([f"Отчёт за период {report['from']} — {report['to']}"])
    w.writerow([])
    w.writerow(["УБОРКИ"])
    w.writerow(["время", "помещение", "зона", "покрытие, %", "сообщение"])
    for c in report["cleanings"]:
        w.writerow([c["ts"], c["room"], c["zone"], c["coverage_pct"], c["message"]])
    w.writerow([])
    w.writerow(["ПРОСРОЧКИ УБОРКИ"])
    w.writerow(["время", "помещение", "зона", "сообщение"])
    for o in report["cleaning_overdue"]:
        w.writerow([o["ts"], o["room"], o["zone"], o["message"]])
    w.writerow([])
    w.writerow(["ХОЛОДОВАЯ ЦЕПЬ"])
    w.writerow(
        ["помещение", "название", "t мин", "t макс", "t средн", "показаний", "вне нормы, мин"]
    )
    for r in report["cold_chain"]:
        w.writerow(
            [
                r["room"],
                r["name"],
                r["t_min"],
                r["t_max"],
                r["t_avg"],
                r["readings"],
                r["out_of_range_min"],
            ]
        )
    return buf.getvalue()
