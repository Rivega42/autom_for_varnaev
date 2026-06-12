"""Проверка дашборда датчиков Grafana (температура/влажность/ИК)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD = REPO_ROOT / "grafana/dashboards/sensors.json"
_PROVIDER = REPO_ROOT / "grafana/provisioning/dashboards/dashboards.yaml"


def _dashboard() -> dict[str, Any]:
    data = json.loads(_DASHBOARD.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_provider_points_to_dashboards_dir() -> None:
    """Провайдер дашбордов указывает на каталог /var/lib/grafana/dashboards."""
    provider = yaml.safe_load(_PROVIDER.read_text(encoding="utf-8"))["providers"][0]
    assert provider["type"] == "file"
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"


def test_dashboard_is_valid_json() -> None:
    """Дашборд — валидный JSON с заголовком и панелями."""
    dash = _dashboard()
    assert dash["title"]
    assert isinstance(dash["panels"], list) and dash["panels"]


def test_dashboard_covers_three_metrics() -> None:
    """Есть панели по air_temp, humidity и surface_ir, запросы к sensor_readings."""
    panels = _dashboard()["panels"]
    queries = " ".join(t["rawSql"] for p in panels for t in p["targets"])
    for metric in ("air_temp", "humidity", "surface_ir"):
        assert metric in queries, f"Нет запроса по метрике {metric}"
    assert "sensor_readings" in queries


def test_dashboard_has_room_filter() -> None:
    """Есть переменная-фильтр по помещению."""
    names = {v["name"] for v in _dashboard()["templating"]["list"]}
    assert "room" in names


def test_panels_switch_to_hourly_rollup_on_long_ranges() -> None:
    """Каждая панель датчиков на длинных диапазонах читает свёртку (#296).

    Один запрос на панель: до 48 ч — сырьё sensor_readings, дольше — почасовой
    continuous aggregate sensor_readings_hourly (avg_value); ветки переключаются
    по ширине выбранного диапазона ($__timeTo() - $__timeFrom()).
    """
    for panel in _dashboard()["panels"]:
        sql = " ".join(t["rawSql"] for t in panel["targets"])
        assert "sensor_readings_hourly" in sql, f"Панель «{panel['title']}» не читает свёртку"
        assert "avg_value" in sql, f"Панель «{panel['title']}» не берёт avg_value из свёртки"
        assert "$__timeFilter(bucket)" in sql, f"Панель «{panel['title']}»: нет фильтра bucket"
        assert "UNION ALL" in sql, f"Панель «{panel['title']}»: нет объединения сырья и свёртки"
        assert sql.count("interval '48 hours'") == 2, (
            f"Панель «{panel['title']}»: обе ветки должны переключаться на границе 48 часов"
        )
