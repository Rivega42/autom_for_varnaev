"""Контроль уборки по расписанию — ядро оценки просрочки (#265).

Санитарный чек-лист под ППК: зона должна убираться не реже, чем раз в N часов, и
покрытие последней уборки — не ниже порога. Если условие нарушено — формируется
событие `cleaning_overdue`. Здесь только ЧИСТАЯ логика (без БД/сети): на вход —
правила, последняя удачная уборка по каждой зоне и набор уже отмеченных зон; на
выход — что нужно сообщить и обновлённый набор отметок (чтобы не спамить каждый
тик). Хранилище правил, выборка событий и эмиссия — в планировщике.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

# Человекочитаемые названия типов зон (как в видеоаналитике/PoC).
_ZONE_RU = {"table": "стол", "floor": "пол", "window": "окно"}


@dataclass(frozen=True)
class CleaningRule:
    """Правило: зона (помещение+тип) должна убираться не реже interval_hours,
    покрытие последней уборки — не ниже min_coverage_pct."""

    room_id: str
    zone_type: str
    interval_hours: float
    min_coverage_pct: int = 0
    zone_name: str | None = None


@dataclass(frozen=True)
class LastCleaning:
    """Последняя зафиксированная уборка зоны (из coverage_report)."""

    ts: datetime
    coverage_pct: int


@dataclass(frozen=True)
class OverdueResult:
    """Найденная просрочка: ключ зоны, причина и готовое сообщение оператору."""

    room_id: str
    zone_type: str
    message: str
    reason: str


def _zone_label(rule: CleaningRule) -> str:
    return rule.zone_name or _ZONE_RU.get(rule.zone_type, rule.zone_type)


def _check(rule: CleaningRule, last: LastCleaning | None, now: datetime) -> str | None:
    """Вернуть причину просрочки (рус.) или None, если зона убрана вовремя."""
    if last is None:
        return "нет данных об уборке"
    elapsed_h = (now - last.ts).total_seconds() / 3600.0
    if elapsed_h > rule.interval_hours:
        return f"не убиралась более {rule.interval_hours:g} ч (прошло {elapsed_h:.1f} ч)"
    if last.coverage_pct < rule.min_coverage_pct:
        return f"покрытие последней уборки {last.coverage_pct}% ниже нормы {rule.min_coverage_pct}%"
    return None


def evaluate_overdue(
    rules: Sequence[CleaningRule],
    last_by_zone: Mapping[tuple[str, str], LastCleaning],
    now: datetime,
    flagged: set[tuple[str, str]],
) -> tuple[list[OverdueResult], set[tuple[str, str]]]:
    """Оценить просрочки уборки.

    `last_by_zone` — последняя удачная уборка по ключу (room_id, zone_type).
    `flagged` — зоны, по которым событие уже отправлено в текущем эпизоде.
    Возвращает (новые просрочки для отправки, обновлённый набор отметок):
    событие шлётся ОДИН раз на эпизод; отметка снимается, когда зона снова в норме.
    """
    results: list[OverdueResult] = []
    new_flagged = set(flagged)
    for rule in rules:
        key = (rule.room_id, rule.zone_type)
        reason = _check(rule, last_by_zone.get(key), now)
        if reason is None:
            new_flagged.discard(key)  # зона в норме — эпизод закрыт
            continue
        if key in new_flagged:
            continue  # уже сообщали в этом эпизоде
        new_flagged.add(key)
        label = _zone_label(rule)
        message = f"Зона «{label}» (помещение {rule.room_id}): {reason}"
        results.append(OverdueResult(rule.room_id, rule.zone_type, message, reason))
    return results, new_flagged
