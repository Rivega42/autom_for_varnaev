"""Демо-«стена роликов»: видеофайлы как «камеры» для ручного видеоанализа (#wall).

Ролики из каталога CLIPS_DIR (монтируется и в api-gateway — отдавать в браузер, и
в воркер video-analytics — читать для file-задания) показываются на дашборде
/ui/wall.html. Каждый ролик представляется «камерой»-записью: так к нему крепятся
ROI-зоны и тумблеры аналитики, а анализ запускается file-заданием с этим camera_id
(полный серверный пайплайн: позы/действия/покрытие/халат).

`rtsp_url` камеры-ролика = `/clips/<файл>` — один и тот же путь отдаёт api-gateway
браузеру и читает воркер (у обоих каталог смонтирован как /clips).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.params import Depends
from sqlalchemy import Engine, insert, select

from api_gateway.cameras_repository import soft_delete_camera
from api_gateway.tables import camera_zones, cameras, rooms
from monitoring_shared import ok

API_PREFIX = "/api/v1"
CLIP_ROOM_ID = "room-clips"
CLIP_ROOM_NAME = "Видео-ролики (демо)"
CLIP_URL_PREFIX = "/clips/"
_VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv"}


def clips_dir() -> Path:
    """Каталог с роликами (env CLIPS_DIR, по умолчанию /clips)."""
    return Path(os.getenv("CLIPS_DIR", "/clips"))


def _ensure_clip_room(engine: Engine) -> None:
    """Создать служебное помещение для роликов, если его ещё нет."""
    with engine.begin() as conn:
        exists = conn.execute(select(rooms.c.id).where(rooms.c.id == CLIP_ROOM_ID)).first()
        if exists is None:
            conn.execute(
                insert(rooms).values(id=CLIP_ROOM_ID, name=CLIP_ROOM_NAME, is_cold=False)
            )


def _zones_for(engine: Engine, camera_id: Any) -> list[dict[str, Any]]:
    """ROI-зоны камеры-ролика в формате API."""
    stmt = select(
        camera_zones.c.id, camera_zones.c.zone_type, camera_zones.c.polygon, camera_zones.c.note
    ).where(camera_zones.c.camera_id == camera_id)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        {"id": r["id"], "zone_type": r["zone_type"], "polygon": r["polygon"], "note": r["note"]}
        for r in rows
    ]


def _ensure_clip_camera(engine: Engine, filename: str) -> dict[str, Any]:
    """Найти или создать «камеру»-ролик для файла; вернуть её запись для API."""
    url = CLIP_URL_PREFIX + filename
    name = Path(filename).stem
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(cameras.c.id, cameras.c.analytics).where(
                    cameras.c.rtsp_url == url, cameras.c.deleted_at.is_(None)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            cam_id = uuid4()
            conn.execute(
                insert(cameras).values(
                    id=cam_id,
                    room_id=CLIP_ROOM_ID,
                    name=name,
                    rtsp_url=url,
                    viewpoint=None,
                    enabled=True,
                    analytics=None,
                )
            )
            analytics: Any = None
        else:
            cam_id = row["id"]
            analytics = row["analytics"]
    return {
        "file": filename,
        "name": name,
        "url": url,
        "camera_id": str(cam_id),
        "analytics": analytics,
        "zones": _zones_for(engine, cam_id),
    }


def _safe_clip_name(name: str) -> str:
    """Имя файла без путей (защита от path traversal) и с видеорасширением."""
    safe = Path(name).name
    if not safe or Path(safe).suffix.lower() not in _VIDEO_EXT:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Ожидается видеофайл (mp4/webm/mov/mkv)",
            },
        )
    return safe


def register_clip_routes(
    app: FastAPI,
    engine: Engine,
    *,
    dependencies: list[Depends],
    admin_dependencies: list[Depends],
) -> None:
    """Зарегистрировать эндпойнты роликов-«камер»: список, загрузка, удаление."""

    @app.get(f"{API_PREFIX}/clips", dependencies=dependencies)
    def list_clips() -> dict[str, Any]:
        """Список видеороликов из CLIPS_DIR; для каждого — «камера»-ролик (id/зоны).

        Каждый mp4/webm в каталоге становится «камерой»: к ней крепятся ROI-зоны и
        тумблеры аналитики, по camera_id запускается file-задание анализа.
        """
        base = clips_dir()
        if not base.is_dir():
            return ok({"clips": [], "dir": str(base), "note": "каталог роликов не примонтирован"})
        _ensure_clip_room(engine)
        files = sorted(p.name for p in base.iterdir() if p.suffix.lower() in _VIDEO_EXT)
        return ok({"clips": [_ensure_clip_camera(engine, f) for f in files], "dir": str(base)})

    @app.post(f"{API_PREFIX}/clips/upload", dependencies=admin_dependencies)
    async def upload_clip(request: Request, name: str = Query(min_length=1)) -> dict[str, Any]:
        """Загрузить видеоролик в CLIPS_DIR (стрим сырого тела, без multipart).

        Браузер шлёт файл телом запроса, имя — в query `name`. Пишем по частям,
        чтобы не держать крупный ролик в памяти, и заводим «камеру»-ролик.
        """
        base = clips_dir()
        if not base.is_dir():
            raise HTTPException(
                status_code=409,
                detail={"code": "CLIPS_DIR_MISSING", "message": "Каталог роликов не примонтирован"},
            )
        safe = _safe_clip_name(name)
        dest = base / safe
        with open(dest, "wb") as fh:  # стрим тела по частям (демо-аплоад)
            async for chunk in request.stream():
                fh.write(chunk)
        _ensure_clip_room(engine)
        cam = _ensure_clip_camera(engine, safe)
        return ok({"uploaded": safe, "camera_id": cam["camera_id"]})

    @app.delete(f"{API_PREFIX}/clips/{{filename}}", dependencies=admin_dependencies)
    def delete_clip(filename: str) -> dict[str, Any]:
        """Удалить ролик «из стены»: файл + мягкое удаление «камеры»-ролика.

        История анализа/событий по камере сохраняется (soft-delete). Файл с тома
        удаляется, поэтому ролик пропадает из списка /clips.
        """
        safe = _safe_clip_name(filename)
        url = CLIP_URL_PREFIX + safe
        with engine.connect() as conn:
            rows = conn.execute(
                select(cameras.c.id).where(
                    cameras.c.rtsp_url == url, cameras.c.deleted_at.is_(None)
                )
            ).all()
        for (cam_id,) in rows:
            soft_delete_camera(engine, cam_id, datetime.now(UTC))
        path = clips_dir() / safe
        removed = path.is_file()
        if removed:
            # НЕ удаляем безвозвратно: переносим в .trash (восстановимо). .trash —
            # подкаталог, в список /clips не попадает (iterdir не рекурсивен).
            trash = clips_dir() / ".trash"
            trash.mkdir(exist_ok=True)
            dest = trash / safe
            if dest.exists():
                dest = trash / f"{uuid4().hex}_{safe}"
            path.rename(dest)
        return ok({"deleted": safe, "file_removed": removed, "cameras": len(rows), "trash": True})
