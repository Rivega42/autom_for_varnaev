"""FastAPI-приложение api-gateway: внешний вход контура (docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Query
from sqlalchemy import Engine

from api_gateway.auth import make_require_api_key
from api_gateway.cameras_repository import get_camera, list_cameras, update_camera
from api_gateway.config import Settings
from api_gateway.db import build_engine
from api_gateway.errors import api_error, register_error_handlers
from api_gateway.events_client import EventsClient, HttpEventsClient
from api_gateway.integration import register_integration_routes
from api_gateway.readings_repository import list_readings
from api_gateway.schemas import (
    AnalysisTaskCreate,
    CameraUpdate,
    CameraZoneCreate,
    CameraZoneUpdate,
)
from api_gateway.tasks_repository import create_task, get_task, list_tasks
from api_gateway.zones_repository import create_zone, delete_zone, list_zones, update_zone
from monitoring_shared import ErrorCode, ok

# Базовый префикс контракта (docs/03_API_CONTRACT.md §1).
API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    events_client: EventsClient | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Создать приложение api-gateway.

    `settings`/`events_client`/`engine` можно передать (для тестов); по умолчанию
    берутся из окружения, поднимается HTTP-клиент к log-service и engine БД.
    """
    settings = settings or Settings.from_env()
    events = events_client or HttpEventsClient(settings.log_service_url)
    engine = engine if engine is not None else build_engine()

    app = FastAPI(title="api-gateway")
    register_error_handlers(app)

    # Зависимость X-API-Key для публичных и /integration/* (docs/03_API_CONTRACT.md §1).
    auth = Depends(make_require_api_key(settings))

    @app.get(f"{API_PREFIX}/health")
    def health() -> dict[str, Any]:
        """Проверка живости сервиса (конверт ok; ключ не требуется)."""
        return ok({"service": "api-gateway", "up": True})

    @app.get(f"{API_PREFIX}/events", dependencies=[auth])
    def get_events(
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        type: str | None = None,
        room: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Лента событий журнала (проксируется к log-service)."""
        data = events.list_events(
            {
                "from": from_,
                "to": to,
                "type": type,
                "room": room,
                "limit": limit,
                "offset": offset,
            }
        )
        return ok(data)

    @app.get(f"{API_PREFIX}/events/{{event_id}}", dependencies=[auth])
    def get_event(event_id: UUID) -> dict[str, Any]:
        """Одно событие по id или 404 EVENT_NOT_FOUND."""
        item = events.get_event(event_id)
        if item is None:
            raise api_error(ErrorCode.EVENT_NOT_FOUND, "Событие не найдено")
        return ok(item)

    @app.post(f"{API_PREFIX}/analysis-tasks", dependencies=[auth])
    def post_analysis_task(body: AnalysisTaskCreate) -> dict[str, Any]:
        """Поставить задание на анализ (status=queued, trigger=manual)."""
        return ok(create_task(engine, body))

    @app.get(f"{API_PREFIX}/analysis-tasks", dependencies=[auth])
    def get_analysis_tasks(
        status: str | None = None,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Список заданий с фильтром по статусу/времени."""
        from_ts = datetime.fromisoformat(from_) if from_ else None
        to_ts = datetime.fromisoformat(to) if to else None
        items, total = list_tasks(
            engine,
            status=status,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
        )
        return ok({"items": items, "total": total})

    @app.get(f"{API_PREFIX}/analysis-tasks/{{task_id}}", dependencies=[auth])
    def get_analysis_task(task_id: UUID) -> dict[str, Any]:
        """Статус/результат задания по id или 404 TASK_NOT_FOUND."""
        item = get_task(engine, task_id)
        if item is None:
            raise api_error(ErrorCode.TASK_NOT_FOUND, "Задание не найдено")
        return ok(item)

    @app.get(f"{API_PREFIX}/readings", dependencies=[auth])
    def get_readings(
        room: str | None = None,
        metric: str | None = None,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Показания датчиков (проверочный путь; основной — Grafana)."""
        from_ts = datetime.fromisoformat(from_) if from_ else None
        to_ts = datetime.fromisoformat(to) if to else None
        items = list_readings(
            engine,
            room=room,
            metric=metric,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )
        return ok({"items": items, "total": len(items)})

    # ── Настройка видеоаналитики: камеры и ROI-зоны (docs/03_API_CONTRACT.md §3.4) ──

    @app.get(f"{API_PREFIX}/cameras", dependencies=[auth])
    def get_cameras() -> dict[str, Any]:
        """Список камер с состоянием (enabled) и тумблерами аналитики."""
        items = list_cameras(engine)
        return ok({"items": items, "total": len(items)})

    @app.get(f"{API_PREFIX}/cameras/{{camera_id}}", dependencies=[auth])
    def get_one_camera(camera_id: UUID) -> dict[str, Any]:
        """Камера по id или 404 CAMERA_NOT_FOUND."""
        item = get_camera(engine, camera_id)
        if item is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        return ok(item)

    @app.patch(f"{API_PREFIX}/cameras/{{camera_id}}", dependencies=[auth])
    def patch_camera(camera_id: UUID, body: CameraUpdate) -> dict[str, Any]:
        """Включить/выключить камеру и функции её видеоаналитики."""
        item = update_camera(engine, camera_id, body)
        if item is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        return ok(item)

    @app.get(f"{API_PREFIX}/cameras/{{camera_id}}/zones", dependencies=[auth])
    def get_camera_zones(camera_id: UUID) -> dict[str, Any]:
        """ROI-зоны камеры (для % покрытия)."""
        if get_camera(engine, camera_id) is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        items = list_zones(engine, camera_id)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/cameras/{{camera_id}}/zones", dependencies=[auth])
    def post_camera_zone(camera_id: UUID, body: CameraZoneCreate) -> dict[str, Any]:
        """Создать ROI-зону камеры."""
        if get_camera(engine, camera_id) is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        return ok(create_zone(engine, camera_id, body))

    @app.patch(f"{API_PREFIX}/zones/{{zone_id}}", dependencies=[auth])
    def patch_zone(zone_id: int, body: CameraZoneUpdate) -> dict[str, Any]:
        """Изменить ROI-зону или 404 ZONE_NOT_FOUND."""
        item = update_zone(engine, zone_id, body)
        if item is None:
            raise api_error(ErrorCode.ZONE_NOT_FOUND, "Зона не найдена")
        return ok(item)

    @app.delete(f"{API_PREFIX}/zones/{{zone_id}}", dependencies=[auth])
    def remove_zone(zone_id: int) -> dict[str, Any]:
        """Удалить ROI-зону или 404 ZONE_NOT_FOUND."""
        if not delete_zone(engine, zone_id):
            raise api_error(ErrorCode.ZONE_NOT_FOUND, "Зона не найдена")
        return ok({"deleted": zone_id})

    # СТЫК-АУРА (v2): заглушённые разъёмы /integration/* (501 при выключенном флаге).
    register_integration_routes(app, settings, dependencies=[auth])

    return app


app = create_app()
