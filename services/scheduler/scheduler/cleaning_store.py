"""Доступ к данным контроля уборки (#265): правила и последние уборки зон.

Правила — таблица cleaning_rules. «Последняя уборка» зоны — последнее событие
coverage_report по (room_id, payload.zone). Фильтрацию по JSON-полю делаем в
Python (диалект-нейтрально: тесты на SQLite, прод на PostgreSQL); из БД берём
только события типа coverage_report за разумное окно.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select

from scheduler.cleaning import CleaningRule, LastCleaning
from scheduler.tables import cleaning_rules, events


def load_cleaning_rules(engine: Engine) -> list[CleaningRule]:
    """Включённые правила контроля уборки."""
    stmt = select(cleaning_rules).where(cleaning_rules.c.enabled.is_(True))
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        CleaningRule(
            room_id=r["room_id"],
            zone_type=r["zone_type"],
            interval_hours=r["interval_hours"],
            min_coverage_pct=r["min_coverage_pct"],
            zone_name=r["zone_name"],
        )
        for r in rows
    ]


def load_last_cleanings(
    engine: Engine,
    rules: list[CleaningRule],
    now: datetime,
) -> dict[tuple[str, str], LastCleaning]:
    """Последняя уборка по каждой зоне из coverage_report-событий.

    Окно выборки — двойной максимальный интервал правил (события старше всё
    равно означают просрочку, их можно не грузить). Payload разбирается в
    Python: {zone, coverage_pct}.
    """
    if not rules:
        return {}
    window_h = max(r.interval_hours for r in rules) * 2
    cutoff = now - timedelta(hours=window_h)
    stmt = (
        select(events.c.ts, events.c.room_id, events.c.payload)
        .where(events.c.type == "coverage_report")
        .where(events.c.ts >= cutoff)
        .order_by(events.c.ts)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    last: dict[tuple[str, str], LastCleaning] = {}
    for ts, room_id, payload in rows:
        if not room_id or not isinstance(payload, dict):
            continue
        zone = payload.get("zone")
        pct = payload.get("coverage_pct")
        if not zone or not isinstance(pct, int | float):
            continue
        if ts.tzinfo is None:  # SQLite может вернуть naive — трактуем как UTC
            ts = ts.replace(tzinfo=UTC)
        key = (room_id, str(zone))
        prev = last.get(key)
        if prev is None or ts >= prev.ts:
            last[key] = LastCleaning(ts=ts, coverage_pct=int(pct))
    return last
