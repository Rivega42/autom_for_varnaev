"""Проверка дашборда видеоаналитики Grafana (analytics.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD = REPO_ROOT / "grafana/dashboards/analytics.json"


def _dashboard() -> dict[str, Any]:
    data = json.loads(_DASHBOARD.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _all_sql() -> str:
    return " ".join(p["targets"][0]["rawSql"] for p in _dashboard()["panels"])


def test_dashboard_is_valid_json() -> None:
    """Дашборд аналитики — валидный JSON с заголовком и панелями."""
    dash = _dashboard()
    assert dash["title"]
    assert isinstance(dash["panels"], list) and dash["panels"]


def test_coverage_panel_uses_coverage_report() -> None:
    """Есть панель «% покрытия» из coverage_report (payload.coverage_pct)."""
    sql = _all_sql()
    assert "coverage_report" in sql
    assert "coverage_pct" in sql


def test_events_panel_filters_analytics() -> None:
    """Лента читает события аналитики из таблицы events (source='analytics')."""
    sql = _all_sql()
    assert "FROM events" in sql
    assert "source='analytics'" in sql or "source = 'analytics'" in sql


def test_uses_timescaledb_datasource_variable() -> None:
    """Дашборд использует ту же datasource-переменную, что и остальные."""
    names = {v["name"] for v in _dashboard()["templating"]["list"]}
    assert "DS_TIMESCALEDB" in names
