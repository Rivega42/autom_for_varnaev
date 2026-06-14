"""Лицензирование (#335): проверка ключа Ed25519, демо-лимиты, enforcement, /license."""

from __future__ import annotations

import base64
import json
from datetime import date

import api_gateway.licensing as lic
import pytest
from api_gateway.app import create_app
from api_gateway.config import Settings
from api_gateway.licensing import evaluate_license, limit_reached
from api_gateway.tables import metadata
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

TODAY = date(2026, 6, 13)


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    """Эфемерная пара: приватный ключ + публичный (hex) для подмены константы."""
    priv = Ed25519PrivateKey.generate()
    pub_hex = (
        priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )
    return priv, pub_hex


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(priv: Ed25519PrivateKey, payload: dict[str, object]) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{_b64url(body)}.{_b64url(priv.sign(body))}"


# ── Ядро: вычисление лицензии ──


def test_no_key_is_demo() -> None:
    """Без ключа — демо-тариф 1/1/1."""
    info = evaluate_license(None, TODAY)
    assert info.status == "demo" and info.tier == "demo"
    assert info.limits == {"rooms": 1, "cameras": 1, "nodes": 1}


def test_valid_key_raises_limits() -> None:
    """Валидный ключ задаёт тарифные лимиты (null = без ограничения)."""
    priv, pub = _keypair()
    key = _sign(
        priv,
        {
            "customer": "Пекарня",
            "tier": "pro",
            "max_rooms": 5,
            "max_cameras": 20,
            "max_nodes": None,
        },
    )
    info = evaluate_license(key, TODAY, public_key_hex=pub)
    assert info.status == "active" and info.tier == "pro" and info.customer == "Пекарня"
    assert info.limits == {"rooms": 5, "cameras": 20, "nodes": None}
    assert limit_reached(info, "cameras", 19) is False
    assert limit_reached(info, "cameras", 20) is True
    assert limit_reached(info, "nodes", 999) is False  # без ограничения


def test_tampered_payload_falls_back_to_demo() -> None:
    """Изменённый payload ломает подпись → демо (invalid)."""
    priv, pub = _keypair()
    key = _sign(priv, {"tier": "pro", "max_cameras": 20})
    _payload_b64, sig = key.split(".")
    forged = json.dumps({"tier": "pro", "max_cameras": 9999}, separators=(",", ":")).encode()
    bad = f"{_b64url(forged)}.{sig}"
    assert evaluate_license(bad, TODAY, public_key_hex=pub).status == "invalid"
    # И мусор вместо ключа — тоже демо.
    assert evaluate_license("не-ключ", TODAY, public_key_hex=pub).status == "invalid"


def test_expired_key_falls_back_to_demo() -> None:
    """Истёкшая подписка → демо-лимиты со статусом expired (данные для GUI целы)."""
    priv, pub = _keypair()
    key = _sign(priv, {"customer": "X", "tier": "pro", "max_cameras": 20, "expires": "2026-01-01"})
    info = evaluate_license(key, TODAY, public_key_hex=pub)
    assert info.status == "expired"
    assert info.limits == {"rooms": 1, "cameras": 1, "nodes": 1}
    assert info.customer == "X" and info.expires == "2026-01-01"


# ── Enforcement через API ──

_SETTINGS = Settings(
    log_service_url="http://log-service:8000", api_key=None, aura_integration_enabled=False
)


def _engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    return eng


def test_demo_limit_blocks_second_camera() -> None:
    """Демо: первая камера заводится, вторая → 409 LICENSE_LIMIT."""
    client = TestClient(create_app(settings=_SETTINGS, engine=_engine()))
    body = {"room": "room-01", "name": "cam-01", "rtsp_url": "rtsp://x"}
    assert client.post("/api/v1/cameras", json=body).status_code == 200
    second = client.post(
        "/api/v1/cameras", json={"room": "room-01", "name": "cam-02", "rtsp_url": "rtsp://y"}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "LICENSE_LIMIT"


def test_license_key_raises_camera_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """С валидным ключом лимит камер поднимается (демо больше не блокирует)."""
    priv, pub = _keypair()
    monkeypatch.setattr(lic, "EMBEDDED_PUBLIC_KEY_HEX", pub)
    key = _sign(priv, {"customer": "X", "tier": "pro", "max_cameras": 5})
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=False,
        license_key=key,
    )
    client = TestClient(create_app(settings=settings, engine=_engine()))
    for i in range(3):
        r = client.post(
            "/api/v1/cameras",
            json={"room": "room-01", "name": f"cam-0{i}", "rtsp_url": "rtsp://x"},
        )
        assert r.status_code == 200, r.text


def test_license_endpoint_reports_tier_and_usage() -> None:
    """GET /license отдаёт тариф, лимиты и расход."""
    client = TestClient(create_app(settings=_SETTINGS, engine=_engine()))
    client.post(
        "/api/v1/cameras", json={"room": "room-01", "name": "cam-01", "rtsp_url": "rtsp://x"}
    )
    data = client.get("/api/v1/license").json()["data"]
    assert data["tier"] == "demo" and data["status"] == "demo"
    assert data["limits"] == {"rooms": 1, "cameras": 1, "nodes": 1}
    assert data["usage"]["cameras"] == 1


# ── Ввод ключа из GUI (PUT /license, хранение в app_config) ──


def test_put_license_key_from_gui_raises_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ключ, введённый через PUT /license, поднимает лимит и виден в GET (демо снято)."""
    priv, pub = _keypair()
    monkeypatch.setattr(lic, "EMBEDDED_PUBLIC_KEY_HEX", pub)
    client = TestClient(create_app(settings=_SETTINGS, engine=_engine()))
    # До ввода ключа — демо: вторая камера блокируется.
    client.post(
        "/api/v1/cameras", json={"room": "room-01", "name": "cam-01", "rtsp_url": "rtsp://x"}
    )
    blocked = client.post(
        "/api/v1/cameras", json={"room": "room-01", "name": "cam-02", "rtsp_url": "rtsp://y"}
    )
    assert blocked.status_code == 409

    key = _sign(priv, {"customer": "Пекарня", "tier": "pro", "max_cameras": 5})
    put = client.put("/api/v1/license", json={"key": key})
    assert put.status_code == 200, put.text
    body = put.json()["data"]
    assert body["tier"] == "pro" and body["status"] == "active" and body["customer"] == "Пекарня"

    # Теперь вторая камера заводится, и GET показывает новый тариф.
    ok_now = client.post(
        "/api/v1/cameras", json={"room": "room-01", "name": "cam-02", "rtsp_url": "rtsp://y"}
    )
    assert ok_now.status_code == 200, ok_now.text
    assert client.get("/api/v1/license").json()["data"]["tier"] == "pro"


def test_put_empty_license_key_resets_to_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой ключ через PUT очищает запись в БД — контур возвращается к демо."""
    priv, pub = _keypair()
    monkeypatch.setattr(lic, "EMBEDDED_PUBLIC_KEY_HEX", pub)
    client = TestClient(create_app(settings=_SETTINGS, engine=_engine()))
    key = _sign(priv, {"customer": "X", "tier": "pro", "max_cameras": 5})
    client.put("/api/v1/license", json={"key": key})
    assert client.get("/api/v1/license").json()["data"]["tier"] == "pro"

    reset = client.put("/api/v1/license", json={"key": ""})
    assert reset.status_code == 200
    assert reset.json()["data"]["tier"] == "demo"
    assert client.get("/api/v1/license").json()["data"]["tier"] == "demo"


def test_db_key_overrides_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ключ из GUI (БД) приоритетнее ключа из переменной окружения LICENSE_KEY."""
    priv, pub = _keypair()
    monkeypatch.setattr(lic, "EMBEDDED_PUBLIC_KEY_HEX", pub)
    env_key = _sign(priv, {"customer": "ENV", "tier": "pro", "max_cameras": 3})
    settings = Settings(
        log_service_url="http://log-service:8000",
        api_key=None,
        aura_integration_enabled=False,
        license_key=env_key,
    )
    client = TestClient(create_app(settings=settings, engine=_engine()))
    assert client.get("/api/v1/license").json()["data"]["customer"] == "ENV"

    gui_key = _sign(priv, {"customer": "GUI", "tier": "ent", "max_cameras": 50})
    client.put("/api/v1/license", json={"key": gui_key})
    assert client.get("/api/v1/license").json()["data"]["customer"] == "GUI"
