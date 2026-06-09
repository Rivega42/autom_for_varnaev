"""FastAPI-приложение api-gateway: внешний вход контура (docs/03_API_CONTRACT.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Query, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from api_gateway.artifacts_repository import get_artifact, insert_artifact
from api_gateway.artifacts_store import (
    build_artifact_path,
    decode_data_url,
    ext_for_mime,
    read_artifact_bytes,
    save_bytes,
)
from api_gateway.auth import make_require_api_key, make_require_api_key_media
from api_gateway.cameras_repository import (
    create_camera,
    get_camera,
    list_cameras,
    update_camera,
)
from api_gateway.config import Settings
from api_gateway.db import build_engine
from api_gateway.errors import api_error, register_error_handlers
from api_gateway.events_client import EventsClient, HttpEventsClient
from api_gateway.integration import register_integration_routes
from api_gateway.readings_repository import list_readings
from api_gateway.rooms_repository import (
    RoomAlreadyExistsError,
    create_room,
    list_rooms,
)
from api_gateway.schedules_repository import (
    DuplicateScheduleNameError,
    create_schedule,
    delete_schedule,
    list_schedules,
    update_schedule,
)
from api_gateway.schemas import (
    AnalysisTaskCreate,
    AnalyticsEventCreate,
    CameraCreate,
    CameraUpdate,
    CameraZoneCreate,
    CameraZoneUpdate,
    RoomCreate,
    ScheduleCreate,
    ScheduleUpdate,
    SensorNodeCreate,
    ThresholdCreate,
    ThresholdUpdate,
)
from api_gateway.sensor_nodes_repository import (
    NodeAlreadyExistsError,
    RoomNotFoundForNodeError,
    create_node,
    list_nodes,
)
from api_gateway.snapshot import Go2rtcSnapshotFetcher, SnapshotFetcher
from api_gateway.stream_proxy import Go2rtcStreamProxy, StreamProxy
from api_gateway.tasks_repository import create_task, get_task, list_tasks
from api_gateway.thresholds_repository import (
    create_threshold,
    delete_threshold,
    list_thresholds,
    update_threshold,
)
from api_gateway.zones_repository import create_zone, delete_zone, list_zones, update_zone
from monitoring_shared import (
    Artifact,
    ArtifactKind,
    ErrorCode,
    Event,
    EventSource,
    EventType,
    ok,
)

# Каталог статического GUI (отдаётся под /ui).
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _parse_query_dt(value: str | None) -> datetime | None:
    """Разобрать ISO-8601 из query-параметра или вернуть 422 VALIDATION_ERROR."""
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise api_error(
            ErrorCode.VALIDATION_ERROR, "Неверный формат даты (ожидается ISO-8601)"
        ) from None


# Базовый префикс контракта (docs/03_API_CONTRACT.md §1).
API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    events_client: EventsClient | None = None,
    engine: Engine | None = None,
    snapshot_fetcher: SnapshotFetcher | None = None,
    stream_proxy: StreamProxy | None = None,
) -> FastAPI:
    """Создать приложение api-gateway.

    `settings`/`events_client`/`engine`/`snapshot_fetcher`/`stream_proxy` можно
    передать (для тестов); по умолчанию берутся из окружения, поднимается
    HTTP-клиент к log-service, engine БД, источник кадров и видеопотока go2rtc.
    """
    settings = settings or Settings.from_env()
    events = events_client or HttpEventsClient(settings.log_service_url)
    engine = engine if engine is not None else build_engine()
    snapshots = snapshot_fetcher or Go2rtcSnapshotFetcher(settings.go2rtc_url)
    streams = stream_proxy or Go2rtcStreamProxy(settings.go2rtc_url)

    app = FastAPI(title="api-gateway")
    register_error_handlers(app)

    # Зависимость X-API-Key для публичных и /integration/* (docs/03_API_CONTRACT.md §1).
    auth = Depends(make_require_api_key(settings))
    # Для медиа-эндпойнтов (кадр/видеопоток): ключ из заголовка ИЛИ query (<img>).
    media_auth = Depends(make_require_api_key_media(settings))

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

    @app.post(f"{API_PREFIX}/analytics-events", dependencies=[auth])
    def post_analytics_event(body: AnalyticsEventCreate) -> dict[str, Any]:
        """Записать событие браузерного живого анализа в журнал (→ Grafana).

        Источник — analytics, тип — action_detected; в payload помечаем
        origin=browser, чтобы отличать от серверного анализа по расписанию.
        Если передан стоп-кадр (`image`) — сохраняем его как артефакт-скриншот и
        прикрепляем к событию (artifact_id + payload.artifact_url для Grafana).
        """
        ts = datetime.now(UTC)
        payload: dict[str, Any] = {**body.payload, "origin": "browser"}
        artifact_id: UUID | None = None

        if body.image is not None:
            try:
                data, mime = decode_data_url(body.image)
            except ValueError as exc:
                raise api_error(ErrorCode.VALIDATION_ERROR, str(exc)) from None
            artifact_id = uuid4()
            path = build_artifact_path(settings.artifacts_dir, ts, artifact_id, ext_for_mime(mime))
            save_bytes(path, data)
            camera_id = payload.get("camera_id")
            insert_artifact(
                engine,
                Artifact(
                    id=artifact_id,
                    created_at=ts,
                    kind=ArtifactKind.SCREENSHOT,
                    path=path,
                    mime=mime,
                    room_id=body.room,
                    camera_id=UUID(camera_id) if isinstance(camera_id, str) else None,
                    task_id=None,
                    meta={"origin": "browser"},
                ),
            )
            payload["artifact_url"] = f"{API_PREFIX}/artifacts/{artifact_id}"

        event = Event(
            id=uuid4(),
            ts=ts,
            source=EventSource.ANALYTICS,
            type=EventType.ACTION_DETECTED,
            room_id=body.room,
            severity=body.severity,
            message=body.message,
            payload=payload,
            artifact_id=artifact_id,
        )
        events.create_event(event)
        return ok({"id": str(event.id), "artifact_id": str(artifact_id) if artifact_id else None})

    @app.get(f"{API_PREFIX}/artifacts/{{artifact_id}}", dependencies=[media_auth])
    def get_artifact_file(artifact_id: UUID) -> Response:
        """Отдать файл артефакта-доказательства (стоп-кадр/overlay) для Grafana/GUI.

        Метаданные берём из таблицы artifacts, файл читаем с общего тома (только
        внутри каталога артефактов). media_auth — ключ из заголовка ИЛИ ?api_key
        (чтобы кадр грузился тегом <img> в дашборде).
        """
        meta = get_artifact(engine, artifact_id)
        if meta is None:
            raise api_error(ErrorCode.ARTIFACT_NOT_FOUND, "Артефакт не найден")
        data = read_artifact_bytes(settings.artifacts_dir, meta["path"])
        if data is None:
            raise api_error(ErrorCode.ARTIFACT_NOT_FOUND, "Файл артефакта недоступен")
        return Response(content=data, media_type=meta.get("mime") or "application/octet-stream")

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
        from_ts = _parse_query_dt(from_)
        to_ts = _parse_query_dt(to)
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
        from_ts = _parse_query_dt(from_)
        to_ts = _parse_query_dt(to)
        items = list_readings(
            engine,
            room=room,
            metric=metric,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )
        return ok({"items": items, "total": len(items)})

    # ── Справочники объекта: помещения и узлы датчиков (docs/03_API_CONTRACT.md §3.4) ──
    # Заводятся через интерфейс/REST — без SQL и сидинга. Без узла в справочнике
    # ingest-sensors отбрасывает его показания, поэтому это часть первичной настройки.

    @app.get(f"{API_PREFIX}/rooms", dependencies=[auth])
    def get_rooms() -> dict[str, Any]:
        """Список помещений."""
        items = list_rooms(engine)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/rooms", dependencies=[auth])
    def post_room(body: RoomCreate) -> dict[str, Any]:
        """Завести помещение или 409 ROOM_ALREADY_EXISTS при занятом id."""
        try:
            return ok(create_room(engine, body))
        except RoomAlreadyExistsError:
            raise api_error(
                ErrorCode.ROOM_ALREADY_EXISTS,
                f"Помещение с id «{body.id}» уже существует",
            ) from None

    @app.get(f"{API_PREFIX}/sensor-nodes", dependencies=[auth])
    def get_sensor_nodes() -> dict[str, Any]:
        """Список узлов датчиков."""
        items = list_nodes(engine)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/sensor-nodes", dependencies=[auth])
    def post_sensor_node(body: SensorNodeCreate) -> dict[str, Any]:
        """Завести узел датчиков (404 если помещения нет, 409 при занятом id)."""
        try:
            return ok(create_node(engine, body))
        except RoomNotFoundForNodeError:
            raise api_error(
                ErrorCode.ROOM_NOT_FOUND,
                f"Помещение «{body.room_id}» не найдено — сначала заведите его",
            ) from None
        except NodeAlreadyExistsError:
            raise api_error(
                ErrorCode.NODE_ALREADY_EXISTS,
                f"Узел с id «{body.id}» уже существует",
            ) from None

    # ── Настройка видеоаналитики: камеры и ROI-зоны (docs/03_API_CONTRACT.md §3.4) ──

    @app.get(f"{API_PREFIX}/cameras", dependencies=[auth])
    def get_cameras() -> dict[str, Any]:
        """Список камер с состоянием (enabled) и тумблерами аналитики."""
        items = list_cameras(engine)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/cameras", dependencies=[auth])
    def post_camera(body: CameraCreate) -> dict[str, Any]:
        """Завести камеру в справочнике объекта (альтернатива сид-конфигу)."""
        return ok(create_camera(engine, body))

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

    @app.get(f"{API_PREFIX}/cameras/{{camera_id}}/snapshot", dependencies=[auth])
    def camera_snapshot(camera_id: UUID) -> Response:
        """JPEG-кадр камеры от go2rtc (фон для разметки ROI в GUI)."""
        camera = get_camera(engine, camera_id)
        if camera is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        image = snapshots.fetch(camera["name"])
        if image is None:
            raise api_error(ErrorCode.INTERNAL, "Кадр-превью недоступен (go2rtc)")
        return Response(content=image, media_type="image/jpeg")

    @app.get(f"{API_PREFIX}/cameras/{{camera_id}}/stream.mjpeg", dependencies=[media_auth])
    async def camera_stream(camera_id: UUID) -> StreamingResponse:
        """Живой MJPEG-видеопоток камеры (прокси go2rtc) для тега <img> в GUI."""
        camera = get_camera(engine, camera_id)
        if camera is None:
            raise api_error(ErrorCode.CAMERA_NOT_FOUND, "Камера не найдена")
        opened = await streams.open(camera["name"])
        if opened is None:
            raise api_error(ErrorCode.INTERNAL, "Видеопоток недоступен (go2rtc)")
        media_type, body = opened
        return StreamingResponse(body, media_type=media_type)

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

    # ── Пороги датчиков (критерии событий) — настройка через интерфейс ──

    @app.get(f"{API_PREFIX}/thresholds", dependencies=[auth])
    def get_thresholds() -> dict[str, Any]:
        """Список порогов."""
        items = list_thresholds(engine)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/thresholds", dependencies=[auth])
    def post_threshold(body: ThresholdCreate) -> dict[str, Any]:
        """Создать порог метрики."""
        return ok(create_threshold(engine, body))

    @app.patch(f"{API_PREFIX}/thresholds/{{threshold_id}}", dependencies=[auth])
    def patch_threshold(threshold_id: int, body: ThresholdUpdate) -> dict[str, Any]:
        """Изменить порог или 404 THRESHOLD_NOT_FOUND."""
        item = update_threshold(engine, threshold_id, body)
        if item is None:
            raise api_error(ErrorCode.THRESHOLD_NOT_FOUND, "Порог не найден")
        return ok(item)

    @app.delete(f"{API_PREFIX}/thresholds/{{threshold_id}}", dependencies=[auth])
    def remove_threshold(threshold_id: int) -> dict[str, Any]:
        """Удалить порог или 404 THRESHOLD_NOT_FOUND."""
        if not delete_threshold(engine, threshold_id):
            raise api_error(ErrorCode.THRESHOLD_NOT_FOUND, "Порог не найден")
        return ok({"deleted": threshold_id})

    # ── Расписания видеоанализа (таймер) — настройка через интерфейс ──

    @app.get(f"{API_PREFIX}/schedules", dependencies=[auth])
    def get_schedules() -> dict[str, Any]:
        """Список расписаний."""
        items = list_schedules(engine)
        return ok({"items": items, "total": len(items)})

    @app.post(f"{API_PREFIX}/schedules", dependencies=[auth])
    def post_schedule(body: ScheduleCreate) -> dict[str, Any]:
        """Создать расписание (таймер запуска видеоанализа) или 409 при дубле имени."""
        try:
            return ok(create_schedule(engine, body))
        except DuplicateScheduleNameError:
            raise api_error(
                ErrorCode.SCHEDULE_DUPLICATE_NAME,
                f"Расписание с именем «{body.name}» уже существует",
            ) from None

    @app.patch(f"{API_PREFIX}/schedules/{{schedule_id}}", dependencies=[auth])
    def patch_schedule(schedule_id: int, body: ScheduleUpdate) -> dict[str, Any]:
        """Изменить расписание или 404 SCHEDULE_NOT_FOUND / 409 при дубле имени."""
        try:
            item = update_schedule(engine, schedule_id, body)
        except DuplicateScheduleNameError as exc:
            raise api_error(
                ErrorCode.SCHEDULE_DUPLICATE_NAME,
                f"Расписание с именем «{exc}» уже существует",
            ) from None
        if item is None:
            raise api_error(ErrorCode.SCHEDULE_NOT_FOUND, "Расписание не найдено")
        return ok(item)

    @app.delete(f"{API_PREFIX}/schedules/{{schedule_id}}", dependencies=[auth])
    def remove_schedule(schedule_id: int) -> dict[str, Any]:
        """Удалить расписание или 404 SCHEDULE_NOT_FOUND."""
        if not delete_schedule(engine, schedule_id):
            raise api_error(ErrorCode.SCHEDULE_NOT_FOUND, "Расписание не найдено")
        return ok({"deleted": schedule_id})

    # СТЫК-АУРА (v2): заглушённые разъёмы /integration/* (501 при выключенном флаге).
    register_integration_routes(app, settings, dependencies=[auth])

    # GUI настройки видеоаналитики (статический SPA). Сам HTML/JS — без ключа;
    # запросы к API из него несут X-API-Key. Каталог создаётся вместе с пакетом.
    if _STATIC_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")

    return app


app = create_app()
