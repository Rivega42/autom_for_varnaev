"""Тесты ядра контроля уборки по расписанию (#265)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scheduler.cleaning import (
    CleaningRule,
    LastCleaning,
    evaluate_overdue,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
RULE = CleaningRule(room_id="room-01", zone_type="table", interval_hours=4, min_coverage_pct=60)
KEY = ("room-01", "table")


def test_overdue_when_no_data() -> None:
    """Нет данных об уборке → просрочка."""
    res, flagged = evaluate_overdue([RULE], {}, NOW, set())
    assert len(res) == 1
    assert "нет данных" in res[0].reason
    assert flagged == {KEY}


def test_overdue_when_interval_exceeded() -> None:
    """Уборка была давно (> интервала) → просрочка."""
    last = {KEY: LastCleaning(ts=NOW - timedelta(hours=5), coverage_pct=90)}
    res, _ = evaluate_overdue([RULE], last, NOW, set())
    assert len(res) == 1 and "более 4 ч" in res[0].message


def test_overdue_when_coverage_below_min() -> None:
    """Свежая уборка, но покрытие ниже нормы → просрочка."""
    last = {KEY: LastCleaning(ts=NOW - timedelta(hours=1), coverage_pct=40)}
    res, _ = evaluate_overdue([RULE], last, NOW, set())
    assert len(res) == 1 and "ниже нормы" in res[0].reason


def test_ok_when_recent_and_covered() -> None:
    """Недавняя уборка с нормальным покрытием → нет события."""
    last = {KEY: LastCleaning(ts=NOW - timedelta(hours=1), coverage_pct=80)}
    res, flagged = evaluate_overdue([RULE], last, NOW, set())
    assert res == [] and flagged == set()


def test_emitted_once_per_episode() -> None:
    """Повторный тик при той же просрочке не дублирует событие."""
    res1, flagged1 = evaluate_overdue([RULE], {}, NOW, set())
    assert len(res1) == 1
    res2, flagged2 = evaluate_overdue([RULE], {}, NOW, flagged1)
    assert res2 == [] and flagged2 == {KEY}


def test_flag_cleared_when_back_to_normal() -> None:
    """После нормальной уборки отметка снимается — новый эпизод сможет сработать."""
    # просрочка → отмечено
    _, flagged = evaluate_overdue([RULE], {}, NOW, set())
    assert flagged == {KEY}
    # зону убрали нормально → отметка снята
    ok_last = {KEY: LastCleaning(ts=NOW, coverage_pct=95)}
    res, flagged = evaluate_overdue([RULE], ok_last, NOW + timedelta(minutes=1), flagged)
    assert res == [] and flagged == set()
    # снова просрочили спустя время → событие приходит заново
    res, _ = evaluate_overdue([RULE], ok_last, NOW + timedelta(hours=6), set())
    assert len(res) == 1


def test_zone_label_russian() -> None:
    """Сообщение содержит русское название зоны и помещение."""
    res, _ = evaluate_overdue([RULE], {}, NOW, set())
    assert "«стол»" in res[0].message and "room-01" in res[0].message
