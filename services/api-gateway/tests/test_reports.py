"""Тесты сменного отчёта (#266): агрегаты, время вне нормы, CSV, эндпойнт."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.reports_repository import build_report, report_to_csv
from api_gateway.tables import events, metadata, rooms, sensor_readings
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

T0 = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
T_END = T0 + timedelta(hours=8)


class _FakeEventsClient:
    def list_events(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"items": [], "total": 0}

    def get_event(self, event_id: UUID) -> dict[str, Any] | None:
        return None

    def create_event(self, event: object) -> None:
        pass

    def ack_event(self, event_id: UUID) -> bool:
        return False


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            rooms.insert(),
            [
                {"id": "cold-01", "name": "Холодильная камера", "is_cold": True},
                {"id": "room-01", "name": "Кухня", "is_cold": False},
            ],
        )
        # показания воздуха в холодильнике: 2..8 °C
        conn.execute(
            sensor_readings.insert(),
            [
                {
                    "ts": T0 + timedelta(hours=h),
                    "node_id": "n1",
                    "room_id": "cold-01",
                    "metric": "air_temp",
                    "value": float(v),
                    "unit": "C",
                }
                for h, v in [(1, 2), (2, 4), (3, 8)]
            ],
        )

        def ev(ts: datetime, type_: str, room: str, payload: dict[str, Any], msg: str) -> dict:
            return {
                "id": uuid4(),
                "ts": ts,
                "source": "sensors" if "threshold" in type_ or "normal" in type_ else "analytics",
                "type": type_,
                "room_id": room,
                "severity": "warning",
                "message": msg,
                "payload": payload,
            }

        conn.execute(
            events.insert(),
            [
                # уборка стола на 80%
                ev(
                    T0 + timedelta(hours=2),
                    "coverage_report",
                    "room-01",
                    {"zone": "table", "zone_id": 1, "coverage_pct": 80},
                    "стол протёрт на 80%",
                ),
                # просрочка пола
                ev(
                    T0 + timedelta(hours=3),
                    "cleaning_overdue",
                    "room-01",
                    {"zone": "floor", "reason": "не убирался"},
                    "Зона «пол»: не убиралась более 8 ч",
                ),
                # вне нормы: 1 час (exceeded → back_to_normal)
                ev(
                    T0 + timedelta(hours=4),
                    "threshold_exceeded",
                    "cold-01",
                    {"metric": "air_temp", "value": 8.0},
                    "температура выше нормы",
                ),
                ev(
                    T0 + timedelta(hours=5),
                    "back_to_normal",
                    "cold-01",
                    {"metric": "air_temp", "value": 4.0},
                    "температура вернулась к норме",
                ),
                # незакрытое превышение за 1 час до конца периода
                ev(
                    T_END - timedelta(hours=1),
                    "threshold_exceeded",
                    "cold-01",
                    {"metric": "air_temp", "value": 9.0},
                    "температура выше нормы",
                ),
            ],
        )


def test_build_report_sections() -> None:
    """Отчёт содержит уборки, просрочки и статистику холодовой цепи."""
    engine = _engine()
    _seed(engine)
    report = build_report(engine, T0, T_END)

    assert len(report["cleanings"]) == 1
    assert report["cleanings"][0]["coverage_pct"] == 80
    assert len(report["cleaning_overdue"]) == 1

    cold = report["cold_chain"]
    assert len(cold) == 1  # только is_cold помещение
    c = cold[0]
    assert c["room"] == "cold-01"
    assert c["t_min"] == 2 and c["t_max"] == 8 and c["readings"] == 3
    # 1 ч закрытый интервал + 1 ч незакрытый до конца периода = 120 мин
    assert c["out_of_range_min"] == 120.0


def test_report_csv_sections() -> None:
    """CSV содержит все разделы и данные."""
    engine = _engine()
    _seed(engine)
    csv_text = report_to_csv(build_report(engine, T0, T_END))
    assert "УБОРКИ" in csv_text
    assert "ПРОСРОЧКИ УБОРКИ" in csv_text
    assert "ХОЛОДОВАЯ ЦЕПЬ" in csv_text
    assert "cold-01" in csv_text and "80" in csv_text


def test_report_endpoint_json_and_csv() -> None:
    """GET /reports/sanitation: JSON в конверте; format=csv — text/csv-вложение."""
    engine = _engine()
    _seed(engine)
    settings = Settings(
        log_service_url="http://log-service:8000", api_key=None, aura_integration_enabled=False
    )
    client = TestClient(
        create_app(settings=settings, events_client=_FakeEventsClient(), engine=engine)
    )

    rj = client.get(
        "/api/v1/reports/sanitation",
        params={"from": T0.isoformat(), "to": T_END.isoformat()},
    )
    assert rj.status_code == 200
    assert rj.json()["data"]["cold_chain"][0]["out_of_range_min"] == 120.0

    rc = client.get(
        "/api/v1/reports/sanitation",
        params={"from": T0.isoformat(), "to": T_END.isoformat(), "format": "csv"},
    )
    assert rc.status_code == 200
    assert rc.headers["content-type"].startswith("text/csv")
    assert "attachment" in rc.headers["content-disposition"]

    bad = client.get(
        "/api/v1/reports/sanitation",
        params={"from": T_END.isoformat(), "to": T0.isoformat()},
    )
    assert bad.status_code == 422
