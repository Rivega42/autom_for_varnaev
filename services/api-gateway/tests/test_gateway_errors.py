"""Проверка обработчиков ошибок api-gateway → единый конверт."""

from __future__ import annotations

from api_gateway.app import create_app
from api_gateway.errors import api_error, error_response, register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from monitoring_shared import ErrorCode


def test_error_response_helper() -> None:
    """error_response даёт статус из карты и конверт-ошибку."""
    resp = error_response(ErrorCode.TASK_NOT_FOUND, "Задание не найдено")
    assert resp.status_code == 404


def test_unknown_route_returns_envelope() -> None:
    """Неизвестный путь → 404 в конверте, а не голый detail."""
    client = TestClient(create_app())
    body = client.get("/api/v1/nope").json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "NOT_FOUND"


class _Body(BaseModel):
    x: int


def _app_with_routes() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/echo")
    def echo(body: _Body) -> dict[str, int]:
        return {"x": body.x}

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise ValueError("упс")

    @app.get("/missing")
    def missing() -> dict[str, str]:
        raise api_error(ErrorCode.EVENT_NOT_FOUND, "Событие не найдено")

    return app


def test_validation_error_envelope() -> None:
    """Невалидное тело → 422 VALIDATION_ERROR в конверте."""
    client = TestClient(_app_with_routes())
    resp = client.post("/echo", json={"x": "не число"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unhandled_exception_envelope() -> None:
    """Непредвиденное исключение → 500 INTERNAL в конверте."""
    client = TestClient(_app_with_routes(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL"


def test_domain_api_error_envelope() -> None:
    """api_error прокидывает доменный код в конверт."""
    client = TestClient(_app_with_routes())
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"
