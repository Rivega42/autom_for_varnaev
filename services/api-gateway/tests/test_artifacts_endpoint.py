"""Тесты отдачи и сохранения артефактов-доказательств (#226).

Проверяем: чистые помощники artifacts_store (data-URL, защита пути), эндпойнт
`GET /artifacts/{id}` (отдаёт файл / 404) и сохранение стоп-кадра при
`POST /analytics-events` с полем image (→ артефакт + ссылка в payload).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from api_gateway.app import create_app
from api_gateway.artifacts_store import (
    build_artifact_path,
    decode_data_url,
    ensure_artifact_dir,
    read_artifact_bytes,
)
from api_gateway.config import Settings
from api_gateway.tables import artifacts as artifacts_table
from fakes import FakeEventsClient
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

# 1×1 PNG (валидный) в base64 — минимальная картинка для проверки сохранения.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"
    "C0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_DATA_URL = "data:image/png;base64," + _PNG_B64


def _sqlite_engine() -> Engine:
    """In-memory SQLite с одной общей связью (StaticPool) и таблицей artifacts."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    artifacts_table.create(engine, checkfirst=True)
    return engine


def _client(tmp_path: Path, events: FakeEventsClient) -> TestClient:
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=False,
        artifacts_dir=str(tmp_path),
    )
    return TestClient(create_app(settings=settings, events_client=events, engine=_sqlite_engine()))


# ---------- чистые помощники ----------


def test_decode_data_url_ok() -> None:
    """Корректный data-URL → байты PNG и mime image/png."""
    data, mime = decode_data_url(_PNG_DATA_URL)
    assert mime == "image/png"
    assert data == base64.b64decode(_PNG_B64)


@pytest.mark.parametrize(
    "bad",
    [
        "нет-префикса",
        "data:image/png,нет-base64",
        "data:application/pdf;base64,AAAA",
        "data:image/png;base64x," + _PNG_B64,  # токен кодирования не 'base64'
    ],
)
def test_decode_data_url_rejects(bad: str) -> None:
    """Мусорный/неподдерживаемый data-URL → ValueError."""
    with pytest.raises(ValueError):
        decode_data_url(bad)


def test_decode_data_url_base64_token_case_insensitive() -> None:
    """Токен BASE64 в любом регистре допустим (mime тоже регистронезависим)."""
    data, mime = decode_data_url("data:image/PNG;BASE64," + _PNG_B64)
    assert mime == "image/png"
    assert data == base64.b64decode(_PNG_B64)


def test_decode_data_url_rejects_oversized() -> None:
    """Картинка больше лимита → ValueError (защита от переполнения диска/памяти)."""
    with pytest.raises(ValueError):
        decode_data_url(_PNG_DATA_URL, max_bytes=1)


def test_read_artifact_bytes_blocks_traversal(tmp_path: Path) -> None:
    """Чтение вне каталога артефактов запрещено (path traversal → None)."""
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("секрет")
    assert read_artifact_bytes(str(tmp_path / "art"), str(outside)) is None


def test_ensure_artifact_dir_permission_error_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Отказ в правах (root-owned том, #380) → внятная ошибка с подсказкой про uid 10001."""

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", _deny)
    with pytest.raises(PermissionError, match="uid 10001"):
        ensure_artifact_dir(str(tmp_path / "2026-06-24" / "x.png"))


def test_build_artifact_path_scheme() -> None:
    """Путь собирается по схеме /<dir>/<YYYY-MM-DD>/<id>.<ext>."""
    aid = UUID("00000000-0000-0000-0000-0000000000aa")
    ts = datetime(2026, 6, 9, tzinfo=UTC)
    assert build_artifact_path("/data/artifacts", ts, aid, "jpg") == (
        f"/data/artifacts/2026-06-09/{aid}.jpg"
    )


# ---------- эндпойнты ----------


def test_get_artifact_404_when_missing(tmp_path: Path) -> None:
    """Несуществующий артефакт → 404 ARTIFACT_NOT_FOUND в конверте."""
    resp = _client(tmp_path, FakeEventsClient()).get(f"/api/v1/artifacts/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"


def test_post_analytics_event_with_image_roundtrip(tmp_path: Path) -> None:
    """POST с image: файл сохранён, событие получило artifact_id + artifact_url,
    и тот же артефакт отдаётся по GET /artifacts/{id}."""
    events = FakeEventsClient()
    client = _client(tmp_path, events)
    cam = uuid4()
    resp = client.post(
        "/api/v1/analytics-events",
        json={
            "room": "room-1",
            "message": "Стол протёрт (двумя руками, 5.0 с)",
            "payload": {"camera_id": str(cam)},
            "image": _PNG_DATA_URL,
        },
    )
    assert resp.status_code == 200
    artifact_id = resp.json()["data"]["artifact_id"]
    assert artifact_id

    # событие ушло в журнал со ссылкой на артефакт
    assert len(events.created) == 1
    ev = events.created[0]
    assert str(ev.artifact_id) == artifact_id
    assert ev.payload["artifact_url"] == f"/api/v1/artifacts/{artifact_id}"
    assert ev.payload["origin"] == "browser"

    # файл реально сохранён на томе и отдаётся по GET
    got = client.get(f"/api/v1/artifacts/{artifact_id}")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.content == base64.b64decode(_PNG_B64)


def test_post_analytics_event_bad_image_422(tmp_path: Path) -> None:
    """Битый data-URL в image → 422 VALIDATION_ERROR, событие не пишется."""
    events = FakeEventsClient()
    resp = _client(tmp_path, events).post(
        "/api/v1/analytics-events",
        json={"room": "r", "message": "x", "image": "data:image/png;base64,@@@"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert events.created == []


def test_post_analytics_event_without_image_unchanged(tmp_path: Path) -> None:
    """Без image поведение прежнее: событие пишется, artifact_id отсутствует."""
    events = FakeEventsClient()
    resp = _client(tmp_path, events).post(
        "/api/v1/analytics-events",
        json={"room": "r", "message": "Машет рукой"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["artifact_id"] is None
    assert events.created[0].artifact_id is None


def test_post_analytics_event_non_uuid_camera_id_ok(tmp_path: Path) -> None:
    """Не-UUID camera_id не валит запрос: артефакт сохраняется, камера не привязана."""
    events = FakeEventsClient()
    resp = _client(tmp_path, events).post(
        "/api/v1/analytics-events",
        json={
            "room": "room-1",
            "message": "Стол протёрт",
            "payload": {"camera_id": "cam-01"},  # человекочитаемый id, не UUID
            "image": _PNG_DATA_URL,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["artifact_id"]
    # событие записано, камера не привязана (camera_id невалиден), но кадр сохранён
    assert events.created[0].artifact_id is not None


def test_post_analytics_event_coverage_report(tmp_path: Path) -> None:
    """type=coverage_report принимается; событие уходит с этим типом и payload зоны."""
    events = FakeEventsClient()
    resp = _client(tmp_path, events).post(
        "/api/v1/analytics-events",
        json={
            "room": "room-1",
            "message": "стол протёрт на 80%",
            "type": "coverage_report",
            "payload": {"zone": "table", "zone_id": 7, "coverage_pct": 80},
        },
    )
    assert resp.status_code == 200
    ev = events.created[0]
    assert ev.type.value == "coverage_report"
    assert ev.payload["coverage_pct"] == 80
    assert ev.payload["origin"] == "browser"


def test_post_analytics_event_unknown_type_422(tmp_path: Path) -> None:
    """Тип вне белого списка → 422, событие не пишется."""
    events = FakeEventsClient()
    resp = _client(tmp_path, events).post(
        "/api/v1/analytics-events",
        json={"room": "r", "message": "x", "type": "pose_event"},
    )
    assert resp.status_code == 422
    assert events.created == []
