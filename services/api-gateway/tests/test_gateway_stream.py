"""Живой MJPEG-видеопоток камеры и медиа-авторизация (ключ из заголовка или query)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.tables import cameras, metadata
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    api_key="secret",
    aura_integration_enabled=False,
)


class _FakeStreamProxy:
    """Фейковый прокси: для потока cam-01 отдаёт MJPEG-байты, иначе None."""

    async def open(self, src: str) -> tuple[str, AsyncIterator[bytes]] | None:
        if src != "cam-01":
            return None

        async def body() -> AsyncIterator[bytes]:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            yield b"jpegbytes"

        return "multipart/x-mixed-replace; boundary=frame", body()


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def _seed(engine: Engine, name: str = "cam-01") -> str:
    cid = uuid4()
    with engine.begin() as conn:
        conn.execute(
            cameras.insert().values(
                id=cid, room_id="room-01", name=name, rtsp_url="rtsp://x", enabled=True
            )
        )
    return str(cid)


def _client(engine: Engine) -> TestClient:
    return TestClient(
        create_app(settings=_SETTINGS, engine=engine, stream_proxy=_FakeStreamProxy())
    )


def test_stream_requires_key() -> None:
    """Без ключа (ни заголовка, ни query) — 401."""
    engine = _engine()
    cid = _seed(engine)
    assert _client(engine).get(f"/api/v1/cameras/{cid}/stream.mjpeg").status_code == 401


def test_stream_key_via_query() -> None:
    """Ключ из query-параметра пропускает (для тега <img>)."""
    engine = _engine()
    cid = _seed(engine)
    resp = _client(engine).get(f"/api/v1/cameras/{cid}/stream.mjpeg?api_key=secret")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert b"jpegbytes" in resp.content


def test_stream_key_via_header() -> None:
    """Ключ из заголовка X-API-Key тоже пропускает."""
    engine = _engine()
    cid = _seed(engine)
    resp = _client(engine).get(
        f"/api/v1/cameras/{cid}/stream.mjpeg", headers={"X-API-Key": "secret"}
    )
    assert resp.status_code == 200


def test_stream_camera_not_found() -> None:
    """Несуществующая камера — 404 CAMERA_NOT_FOUND."""
    engine = _engine()
    _seed(engine)
    resp = _client(engine).get(f"/api/v1/cameras/{uuid4()}/stream.mjpeg?api_key=secret")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CAMERA_NOT_FOUND"


def test_stream_unavailable() -> None:
    """go2rtc недоступен/нет потока — 500 INTERNAL."""
    engine = _engine()
    cid = _seed(engine, name="cam-02")  # прокси отдаёт None для не-cam-01
    resp = _client(engine).get(f"/api/v1/cameras/{cid}/stream.mjpeg?api_key=secret")
    assert resp.status_code == 500
