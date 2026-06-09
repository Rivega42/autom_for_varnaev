"""Сиды справочников и порогов из конфигурации объекта.

Читает YAML-конфиг (rooms/sensor_nodes/cameras/thresholds), валидирует моделями
monitoring_shared и идемпотентно загружает их в БД. Справочники — UPSERT по
первичному ключу; пороги (без естественного ключа) — вставка, если идентичного
ещё нет. Без флага --apply выполняется только разбор и валидация (dry-run) — это
и покрывается тестами; реальная запись в БД требует доступной TimescaleDB.

Запуск:
    python scripts/seed.py db/seeds/object.example.yaml          # dry-run
    python scripts/seed.py db/seeds/object.yaml --apply          # запись в БД
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

import yaml
from pydantic import BaseModel

from monitoring_shared import Camera, Metric, Room, SensorNode, Severity, ThresholdOp


class ThresholdSeed(BaseModel):
    """Порог датчика из конфига объекта (room=None — глобальный порог)."""

    room: str | None = None
    metric: Metric
    op: ThresholdOp
    value: float
    severity: Severity = Severity.WARNING
    silent_min: int | None = None
    enabled: bool = True


# SQL-команды UPSERT (идемпотентность по первичному ключу).
_UPSERT_ROOM = (
    "INSERT INTO rooms (id, name, is_cold) VALUES (:id, :name, :is_cold) "
    "ON CONFLICT (id) DO UPDATE SET "
    "name = EXCLUDED.name, is_cold = EXCLUDED.is_cold"
)
_UPSERT_NODE = (
    "INSERT INTO sensor_nodes (id, room_id, placement, power, note) "
    "VALUES (:id, :room_id, :placement, :power, :note) "
    "ON CONFLICT (id) DO UPDATE SET "
    "room_id = EXCLUDED.room_id, placement = EXCLUDED.placement, "
    "power = EXCLUDED.power, note = EXCLUDED.note"
)
_UPSERT_CAMERA = (
    "INSERT INTO cameras (id, room_id, name, rtsp_url, viewpoint, enabled) "
    "VALUES (:id, :room_id, :name, :rtsp_url, CAST(:viewpoint AS JSONB), :enabled) "
    "ON CONFLICT (id) DO UPDATE SET "
    "room_id = EXCLUDED.room_id, name = EXCLUDED.name, "
    "rtsp_url = EXCLUDED.rtsp_url, viewpoint = EXCLUDED.viewpoint, "
    "enabled = EXCLUDED.enabled"
)
# Пороги не имеют естественного ключа — вставляем, только если идентичного
# (по room_id+metric+op+value) ещё нет, чтобы повторный сид не плодил дубли и не
# затирал пороги, заведённые оператором через GUI.
_INSERT_THRESHOLD_IF_ABSENT = (
    "INSERT INTO thresholds (room_id, metric, op, value, severity, silent_min, enabled) "
    "SELECT :room, :metric, :op, :value, :severity, :silent_min, :enabled "
    "WHERE NOT EXISTS ("
    "SELECT 1 FROM thresholds "
    "WHERE room_id IS NOT DISTINCT FROM :room AND metric = :metric "
    "AND op = :op AND value = :value)"
)


def load_config(
    path: str | Path,
) -> tuple[list[Room], list[SensorNode], list[Camera], list[ThresholdSeed]]:
    """Прочитать и провалидировать конфиг объекта."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rooms = [Room(**item) for item in data.get("rooms", [])]
    nodes = [SensorNode(**item) for item in data.get("sensor_nodes", [])]
    cameras = [Camera(**item) for item in data.get("cameras", [])]
    thresholds = [ThresholdSeed(**item) for item in data.get("thresholds", [])]
    return rooms, nodes, cameras, thresholds


def _database_url() -> str:
    """Собрать URL подключения к БД из окружения (как в Alembic env.py)."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = quote(os.getenv("POSTGRES_USER", "monitoring"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "monitoring")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def apply(
    rooms: list[Room],
    nodes: list[SensorNode],
    cameras: list[Camera],
    thresholds: list[ThresholdSeed] | None = None,
) -> None:
    """Идемпотентно записать справочники (UPSERT по id) и пороги (вставка без дублей)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(_database_url())
    with engine.begin() as conn:
        for room in rooms:
            conn.execute(
                text(_UPSERT_ROOM),
                {"id": room.id, "name": room.name, "is_cold": room.is_cold},
            )
        for node in nodes:
            conn.execute(
                text(_UPSERT_NODE),
                {
                    "id": node.id,
                    "room_id": node.room_id,
                    "placement": node.placement,
                    "power": node.power,
                    "note": node.note,
                },
            )
        for camera in cameras:
            viewpoint = json.dumps(camera.viewpoint) if camera.viewpoint is not None else None
            conn.execute(
                text(_UPSERT_CAMERA),
                {
                    "id": str(camera.id),
                    "room_id": camera.room_id,
                    "name": camera.name,
                    "rtsp_url": camera.rtsp_url,
                    "viewpoint": viewpoint,
                    "enabled": camera.enabled,
                },
            )
        for threshold in thresholds or []:
            conn.execute(
                text(_INSERT_THRESHOLD_IF_ABSENT),
                {
                    "room": threshold.room,
                    "metric": threshold.metric.value,
                    "op": threshold.op.value,
                    "value": threshold.value,
                    "severity": threshold.severity.value,
                    "silent_min": threshold.silent_min,
                    "enabled": threshold.enabled,
                },
            )


def main() -> None:
    """CLI-точка: разобрать конфиг и (опционально) записать в БД."""
    parser = argparse.ArgumentParser(description="Сиды справочников из конфига объекта")
    parser.add_argument("config", help="путь к YAML-конфигу объекта")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="записать в БД (иначе только проверка)",
    )
    args = parser.parse_args()

    rooms, nodes, cameras, thresholds = load_config(args.config)
    print(
        f"Прочитано: помещений={len(rooms)}, узлов={len(nodes)}, "
        f"камер={len(cameras)}, порогов={len(thresholds)}"
    )
    if args.apply:
        apply(rooms, nodes, cameras, thresholds)
        print("Справочники и пороги записаны в БД.")
    else:
        print("Режим проверки (dry-run): запись не выполнялась. Для записи добавьте --apply.")


if __name__ == "__main__":
    main()
