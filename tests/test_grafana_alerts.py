"""Проверка provisioning алертов Grafana (E7.5): пороги и тишина датчиков."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_ALERTS = REPO_ROOT / "grafana/provisioning/alerting/rules.yaml"
_DATASOURCE = REPO_ROOT / "grafana/provisioning/datasources/timescaledb.yaml"


def _rules() -> list[dict[str, Any]]:
    """Собрать все правила из всех групп файла алертов."""
    data = yaml.safe_load(_ALERTS.read_text(encoding="utf-8"))
    return [rule for group in data["groups"] for rule in group["rules"]]


def _rule_sql(rule: dict[str, Any]) -> str:
    """Склеить все SQL-запросы правила в одну строку для проверок."""
    return " ".join(item["model"]["rawSql"] for item in rule["data"] if "rawSql" in item["model"])


def test_alerts_yaml_is_valid() -> None:
    """Файл алертов — валидный YAML с apiVersion и непустыми группами правил."""
    data = yaml.safe_load(_ALERTS.read_text(encoding="utf-8"))
    assert data["apiVersion"] == 1
    assert data["groups"] and all(group["rules"] for group in data["groups"])


def test_datasource_has_stable_uid() -> None:
    """У datasource зафиксирован uid, на который ссылаются алерты."""
    ds = yaml.safe_load(_DATASOURCE.read_text(encoding="utf-8"))["datasources"][0]
    assert ds["uid"] == "timescaledb"


def test_two_rules_threshold_and_silence() -> None:
    """Есть два правила: превышение порога и молчание датчика."""
    uids = {rule["uid"] for rule in _rules()}
    assert "sensors-threshold-exceeded" in uids
    assert "sensors-node-silent" in uids


def test_rules_query_correct_tables() -> None:
    """Порог читает thresholds+sensor_readings, тишина — sensor_nodes+silent_min."""
    rules = {rule["uid"]: rule for rule in _rules()}
    thr_sql = _rule_sql(rules["sensors-threshold-exceeded"])
    assert "thresholds" in thr_sql and "sensor_readings" in thr_sql
    sil_sql = _rule_sql(rules["sensors-node-silent"])
    assert "sensor_nodes" in sil_sql and "silent_min" in sil_sql


def test_rules_reference_datasource_and_condition() -> None:
    """Каждое правило ссылается на datasource uid и имеет условие срабатывания."""
    for rule in _rules():
        ds_uids = {item.get("datasourceUid") for item in rule["data"]}
        assert "timescaledb" in ds_uids
        assert rule["condition"]
