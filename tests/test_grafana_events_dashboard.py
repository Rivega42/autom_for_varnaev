"""Проверка дашборда ленты событий Grafana."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD = REPO_ROOT / "grafana/dashboards/events.json"


def _dashboard() -> dict[str, Any]:
    data = json.loads(_DASHBOARD.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_dashboard_is_valid_json() -> None:
    """Дашборд событий — валидный JSON с заголовком и панелями."""
    dash = _dashboard()
    assert dash["title"]
    assert isinstance(dash["panels"], list) and dash["panels"]


def test_dashboard_queries_events_table() -> None:
    """Панель-таблица читает из events с полями журнала."""
    panel = _dashboard()["panels"][0]
    assert panel["type"] == "table"
    sql = panel["targets"][0]["rawSql"]
    assert "events" in sql
    assert "message" in sql
    assert "severity" in sql


def test_dashboard_has_filters() -> None:
    """Есть фильтры по помещению, типу и важности."""
    names = {v["name"] for v in _dashboard()["templating"]["list"]}
    assert {"room", "type", "severity"} <= names
