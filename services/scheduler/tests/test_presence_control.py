"""Тесты ядра контроля присутствия по окну времени (#300)."""

from __future__ import annotations

from datetime import UTC, datetime, time

from scheduler.presence_control import PresenceRule, evaluate_missing

RULE = PresenceRule(
    id=1,
    room_id="room-01",
    window_start=time(8, 0),
    window_end=time(17, 0),
    max_absence_min=30,
    room_name="Цех приготовления",
)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 11, hour, minute, tzinfo=UTC)


def test_outside_window_no_event() -> None:
    """Вне окна (до начала и после конца) отсутствие не считается нарушением."""
    for now in (_at(7, 59), _at(17, 0), _at(23, 30)):
        results, flagged = evaluate_missing([RULE], {}, now, set())
        assert results == [] and flagged == set()


def test_missing_after_threshold_once_per_episode() -> None:
    """Нет присутствия дольше порога → одно событие на эпизод (без спама)."""
    # 8:29 — с начала окна прошло 29 мин < 30 — рано
    results, flagged = evaluate_missing([RULE], {}, _at(8, 29), set())
    assert results == []
    # 8:30 — порог достигнут → событие
    results, flagged = evaluate_missing([RULE], {}, _at(8, 30), flagged)
    assert len(results) == 1
    missing = results[0]
    assert missing.room_id == "room-01"
    assert missing.absent_for_min == 30
    assert "Цех приготовления" in missing.message
    assert "08:00–17:00" in missing.message
    # следующий тик того же эпизода — тишина
    results, flagged = evaluate_missing([RULE], {}, _at(8, 31), flagged)
    assert results == []


def test_presence_resets_episode_and_anchor() -> None:
    """Присутствие закрывает эпизод; новый перерыв отсчитывается от него."""
    flagged = {RULE.id}  # по эпизоду уже сообщали
    last = {"room-01": _at(10, 0)}
    # 10:20 — перерыв 20 мин < 30 → эпизод закрыт, события нет
    results, flagged = evaluate_missing([RULE], last, _at(10, 20), flagged)
    assert results == [] and flagged == set()
    # 10:31 — перерыв 31 мин от последнего присутствия → новое событие
    results, flagged = evaluate_missing([RULE], last, _at(10, 31), flagged)
    assert len(results) == 1
    assert results[0].absent_for_min == 31


def test_presence_before_window_ignored() -> None:
    """Присутствие ДО начала окна не считается: отсчёт от начала окна."""
    last = {"room-01": _at(6, 0)}  # было присутствие в 6 утра, окно с 8
    results, _ = evaluate_missing([RULE], last, _at(8, 30), set())
    assert len(results) == 1  # 30 мин от 8:00, а не от 6:00
    assert results[0].absent_for_min == 30


def test_exit_window_closes_episode() -> None:
    """Выход из окна снимает отметку: на следующий день событие повторится."""
    _, flagged = evaluate_missing([RULE], {}, _at(8, 30), set())
    assert flagged == {RULE.id}
    _, flagged = evaluate_missing([RULE], {}, _at(17, 5), flagged)
    assert flagged == set()


def test_naive_last_presence_treated_as_utc() -> None:
    """Naive-время последнего присутствия трактуется как UTC (SQLite)."""
    last = {"room-01": datetime(2026, 6, 11, 10, 0)}  # naive
    results, _ = evaluate_missing([RULE], last, _at(10, 31), set())
    assert len(results) == 1


def test_rules_independent() -> None:
    """Правила независимы: отметка одного не гасит событие другого."""
    other = PresenceRule(
        id=2,
        room_id="room-02",
        window_start=time(8, 0),
        window_end=time(17, 0),
        max_absence_min=10,
    )
    results, flagged = evaluate_missing([RULE, other], {}, _at(8, 15), {RULE.id})
    # RULE уже отмечен (и порог 30 не достигнут — эпизод закрыт), other — событие
    assert [r.rule_id for r in results] == [2]
    assert results[0].message.startswith("В помещении room-02")
    assert flagged == {2}
