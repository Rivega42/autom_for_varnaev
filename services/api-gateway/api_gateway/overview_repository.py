"""Сборка обзора объекта для дежурного (#288).

Один агрегат вместо пяти запросов из браузера: помещения с последними
показаниями, узлы и камеры с признаком «на связи», лента последних событий и
число активных (неподтверждённых) алертов. Живость узлов выводится из свежести
последнего показания (отдельного события «узел вернулся» нет); живость камер —
из последних событий camera_offline/camera_online (#283); события берутся из
log-service через events_client.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine

from api_gateway.cameras_repository import list_cameras
from api_gateway.events_client import EventsClient
from api_gateway.readings_repository import latest_readings
from api_gateway.rooms_repository import list_rooms
from api_gateway.sensor_nodes_repository import list_nodes

# Важности, которые считаем «алертами» (для счётчика активных).
_ALERT_SEVERITIES = frozenset({"warning", "critical"})


def _as_utc(value: datetime) -> datetime:
    """Naive-время (SQLite) считаем UTC; aware — без изменений."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _camera_online_state(events: list[dict[str, Any]]) -> dict[str, bool]:
    """Свести последнее состояние камер из событий camera_offline/camera_online.

    События отсортированы по убыванию времени, поэтому первое встреченное по
    данной камере — самое свежее; online = последним был camera_online.
    """
    state: dict[str, bool] = {}
    for ev in events:
        type_ = ev.get("type")
        if type_ not in ("camera_offline", "camera_online"):
            continue
        camera_id = (ev.get("payload") or {}).get("camera_id")
        if camera_id and camera_id not in state:
            state[camera_id] = type_ == "camera_online"
    return state


def build_overview(
    engine: Engine,
    events_client: EventsClient,
    now: datetime,
    *,
    node_silent_min: int = 10,
    recent_limit: int = 20,
    scan_limit: int = 200,
) -> dict[str, Any]:
    """Собрать обзор объекта (см. docs/03_API_CONTRACT.md §3.9)."""
    node_latest, room_metric = latest_readings(engine)

    # Последние события журнала — единый источник для ленты, алертов и камер.
    payload = events_client.list_events({"limit": scan_limit})
    events = payload.get("items", []) if isinstance(payload, dict) else []
    events_sorted = sorted(events, key=lambda e: str(e.get("ts", "")), reverse=True)

    active_alerts = sum(
        1
        for e in events_sorted
        if e.get("severity") in _ALERT_SEVERITIES and not e.get("acknowledged_at")
    )
    cam_state = _camera_online_state(events_sorted)

    # Помещения с последними показаниями по метрикам.
    rooms = []
    for room in list_rooms(engine):
        metrics = {
            metric: value
            for (room_id, metric), value in room_metric.items()
            if room_id == room["id"]
        }
        rooms.append({**room, "metrics": metrics})

    # Узлы: «на связи», если показание свежее порога тишины.
    threshold = timedelta(minutes=node_silent_min)
    nodes = []
    for node in list_nodes(engine):
        last = node_latest.get(node["id"])
        online = last is not None and (_as_utc(now) - _as_utc(last)) <= threshold
        nodes.append(
            {
                "id": node["id"],
                "room_id": node["room_id"],
                "online": online,
                "last_ts": _as_utc(last).isoformat() if last is not None else None,
            }
        )

    # Камеры: «на связи» по последнему событию живости (нет события → считаем на связи).
    cameras = [
        {
            "id": cam["id"],
            "name": cam["name"],
            "room_id": cam["room"],
            "enabled": cam["enabled"],
            "online": cam_state.get(cam["id"], True),
        }
        for cam in list_cameras(engine)
    ]

    return {
        "now": _as_utc(now).isoformat(),
        "rooms": rooms,
        "nodes": nodes,
        "cameras": cameras,
        "recent_events": events_sorted[:recent_limit],
        "active_alerts": active_alerts,
    }
