"""Тесты монитора живости камер (#283): эпизоды offline/online, дедуп, текст."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import sqlalchemy as sa
from scheduler.camera_liveness import CameraLivenessMonitor
from scheduler.camera_store import Go2rtcCameraProber
from scheduler.tables import cameras, metadata, rooms
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from monitoring_shared import Event

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return engine


def _add_camera(engine: Engine, name: str, room_id: str = "room-01", enabled: bool = True) -> str:
    cam_id = uuid4()
    with engine.begin() as conn:
        # помещение заводим один раз (несколько камер могут жить в одном)
        exists = conn.execute(sa.select(rooms.c.id).where(rooms.c.id == room_id)).first()
        if exists is None:
            conn.execute(rooms.insert().values(id=room_id, name="Цех приготовления"))
        conn.execute(
            cameras.insert().values(id=cam_id, room_id=room_id, name=name, enabled=enabled)
        )
    return str(cam_id)


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _FakeProber:
    """Фейковая проба: живость задаётся флагом, переключается в тесте."""

    def __init__(self, live: bool = True) -> None:
        self.live = live

    def is_live(self, stream_name: str) -> bool:
        return self.live


def test_offline_emits_once_then_online_on_recovery() -> None:
    """Отвал → camera_offline один раз; восстановление → camera_online; новый отвал → снова."""
    engine = _engine()
    _add_camera(engine, "Кухня-1")
    sink = _CollectingSink()
    prober = _FakeProber(live=False)
    monitor = CameraLivenessMonitor(sink, prober)

    # камера не отвечает → одно событие camera_offline
    assert monitor.check(engine, NOW) == 1
    assert monitor.check(engine, NOW) == 0  # эпизод тот же — повтора нет
    off = sink.events[0]
    assert off.type.value == "camera_offline"
    assert off.severity.value == "warning"
    assert "Кухня-1" in off.message
    assert "Цех приготовления" in off.message
    assert off.payload["camera_name"] == "Кухня-1"
    assert off.room_id == "room-01"  # room_id события = room_id камеры

    # камера вернулась → camera_online (снятие)
    prober.live = True
    assert monitor.check(engine, NOW) == 1
    on = sink.events[1]
    assert on.type.value == "camera_online"
    assert on.severity.value == "info"
    assert monitor.check(engine, NOW) == 0  # на связи и не была помечена — тишина

    # снова упала → новый эпизод, новое событие
    prober.live = False
    assert monitor.check(engine, NOW) == 1
    assert len(sink.events) == 3
    assert sink.events[2].type.value == "camera_offline"


def test_live_camera_no_events() -> None:
    """Камера на связи с самого начала — событий нет."""
    engine = _engine()
    _add_camera(engine, "Кухня-1")
    sink = _CollectingSink()
    assert CameraLivenessMonitor(sink, _FakeProber(live=True)).check(engine, NOW) == 0
    assert sink.events == []


class _PerCameraProber:
    """Проба с разным результатом по имени камеры (для проверки покамерного ключа)."""

    def __init__(self, live_by_name: dict[str, bool]) -> None:
        self.live_by_name = live_by_name

    def is_live(self, stream_name: str) -> bool:
        return self.live_by_name.get(stream_name, False)


def test_mixed_liveness_keyed_per_camera() -> None:
    """В одном тике разные камеры дают независимые события (ключ — id камеры)."""
    engine = _engine()
    _add_camera(engine, "Кухня-1", room_id="room-01")
    _add_camera(engine, "Склад-2", room_id="room-01")
    sink = _CollectingSink()
    prober = _PerCameraProber({"Кухня-1": True, "Склад-2": False})
    monitor = CameraLivenessMonitor(sink, prober)

    # упала только Склад-2 → одно событие
    assert monitor.check(engine, NOW) == 1
    assert sink.events[0].payload["camera_name"] == "Склад-2"
    # теперь падает Кухня-1, Склад-2 восстановилась → два события за тик
    prober.live_by_name = {"Кухня-1": False, "Склад-2": True}
    assert monitor.check(engine, NOW) == 2
    kinds = {e.payload["camera_name"]: e.type.value for e in sink.events[1:]}
    assert kinds == {"Кухня-1": "camera_offline", "Склад-2": "camera_online"}


def test_disabled_cameras_ignored() -> None:
    """Выключенные камеры не проверяются."""
    engine = _engine()
    _add_camera(engine, "Кухня-1", enabled=False)
    sink = _CollectingSink()
    assert CameraLivenessMonitor(sink, _FakeProber(live=False)).check(engine, NOW) == 0
    assert sink.events == []


class _FakeResp:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


class _FakeHttpClient:
    """Минимальный httpx-подобный клиент для пробы (фиксированный ответ)."""

    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any]) -> _FakeResp:
        self.calls.append({"url": url, "params": params})
        return self._resp


def test_prober_live_on_200_with_body() -> None:
    """200 с непустым телом = камера на связи; запрос идёт на frame.jpeg по имени."""
    client = _FakeHttpClient(_FakeResp(200, b"\xff\xd8jpeg"))
    prober = Go2rtcCameraProber("http://media-gateway:1984", client=client)
    assert prober.is_live("Кухня-1") is True
    assert client.calls[0]["url"].endswith("/api/frame.jpeg")
    assert client.calls[0]["params"] == {"src": "Кухня-1"}


def test_prober_offline_on_non_200_or_empty() -> None:
    """Не-200 или пустое тело = камера недоступна."""
    assert (
        Go2rtcCameraProber("http://x", client=_FakeHttpClient(_FakeResp(404, b""))).is_live("c")
        is False
    )
    assert (
        Go2rtcCameraProber("http://x", client=_FakeHttpClient(_FakeResp(200, b""))).is_live("c")
        is False
    )


class _RaisingHttpClient:
    """Клиент, имитирующий недоступность go2rtc (httpx.HTTPError)."""

    def get(self, url: str, params: dict[str, Any]) -> Any:
        raise httpx.ConnectError("media-gateway недоступен")


def test_prober_offline_on_http_error() -> None:
    """Сетевой сбой пробы (go2rtc недоступен) трактуется как «камера недоступна»."""
    prober = Go2rtcCameraProber("http://x", client=_RaisingHttpClient())
    assert prober.is_live("Кухня-1") is False


def test_room_name_falls_back_to_id() -> None:
    """Без имени помещения текст использует room_id (камера без привязки к rooms)."""
    engine = _engine()
    cam_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            cameras.insert().values(id=cam_id, room_id="room-99", name="Склад", enabled=True)
        )
    sink = _CollectingSink()
    CameraLivenessMonitor(sink, _FakeProber(live=False)).check(engine, NOW)
    assert "room-99" in sink.events[0].message
