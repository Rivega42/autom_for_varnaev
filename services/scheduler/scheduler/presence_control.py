"""Контроль присутствия в рабочей зоне по окну времени — ядро оценки (#300).

В помещении в заданное окно (например, рабочая смена 08:00–17:00) присутствие
персонала должно фиксироваться не реже, чем раз в `max_absence_min` минут.
Присутствие поставляет видеоаналитика: события `presence_detected` от рабочих
зон (#302). Если внутри окна присутствия нет дольше допустимого перерыва —
формируется событие `presence_missing`.

Здесь только ЧИСТАЯ логика (без БД/сети): на вход — правила, время последнего
присутствия по помещениям и набор уже отмеченных правил; на выход — что нужно
сообщить и обновлённый набор отметок (раз на эпизод, без спама каждый тик).
Хранилище правил, выборка событий и эмиссия — в планировщике.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time


def _as_utc(dt: datetime) -> datetime:
    """Привести время к aware (naive трактуем как UTC) — иначе сравнение
    naive и aware datetime бросает TypeError."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass(frozen=True)
class PresenceRule:
    """Правило: в помещении в окне window_start–window_end присутствие должно
    фиксироваться не реже, чем раз в max_absence_min минут."""

    id: int
    room_id: str
    window_start: time
    window_end: time
    max_absence_min: int
    room_name: str | None = None


@dataclass(frozen=True)
class MissingResult:
    """Найденное отсутствие: ключ правила и готовое сообщение оператору."""

    rule_id: int
    room_id: str
    message: str
    window: str  # "08:00–17:00" (для payload)
    absent_for_min: int


def _window_label(rule: PresenceRule) -> str:
    return f"{rule.window_start:%H:%M}–{rule.window_end:%H:%M}"


def _room_label(rule: PresenceRule) -> str:
    return rule.room_name or rule.room_id


def evaluate_missing(
    rules: Sequence[PresenceRule],
    last_presence: Mapping[str, datetime],
    now: datetime,
    flagged: set[int],
) -> tuple[list[MissingResult], set[int]]:
    """Оценить отсутствие присутствия в окнах правил.

    `now` — aware-время в часовом поясе, в котором заданы окна правил
    (PRESENCE_TZ). `last_presence` — время последнего presence_detected по
    room_id (UTC). `flagged` — id правил, по которым событие уже отправлено в
    текущем эпизоде. Возвращает (новые отсутствия, обновлённые отметки):
    событие шлётся ОДИН раз на эпизод; отметка снимается при новом присутствии
    или по выходе из окна — на следующем окне/эпизоде сообщение повторится.
    """
    results: list[MissingResult] = []
    new_flagged = set(flagged)
    for rule in rules:
        if not (rule.window_start <= now.time() < rule.window_end):
            new_flagged.discard(rule.id)  # вне окна — эпизод закрыт
            continue
        window_start_dt = now.replace(
            hour=rule.window_start.hour,
            minute=rule.window_start.minute,
            second=0,
            microsecond=0,
        )
        # Точка отсчёта перерыва: последнее присутствие внутри окна, иначе начало окна.
        anchor = window_start_dt
        last = last_presence.get(rule.room_id)
        if last is not None:
            last = _as_utc(last)
            if last > anchor:
                anchor = last
        absent_min = int((now - anchor).total_seconds() // 60)
        if absent_min < rule.max_absence_min:
            new_flagged.discard(rule.id)  # присутствие есть — эпизод закрыт
            continue
        if rule.id in new_flagged:
            continue  # уже сообщали в этом эпизоде
        new_flagged.add(rule.id)
        window = _window_label(rule)
        message = (
            f"В помещении {_room_label(rule)} нет присутствия в рабочей зоне "
            f"{absent_min} мин (окно {window}, допустимо {rule.max_absence_min} мин)"
        )
        results.append(
            MissingResult(
                rule_id=rule.id,
                room_id=rule.room_id,
                message=message,
                window=window,
                absent_for_min=absent_min,
            )
        )
    return results, new_flagged
