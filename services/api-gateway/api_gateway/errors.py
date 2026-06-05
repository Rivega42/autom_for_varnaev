"""Обработчики ошибок api-gateway: любая ошибка — в едином конверте (§1.1–§1.2).

Доменные эндпойнты бросают `api_error(code, message)` с кодами из `ErrorCode`;
ошибки валидации тела и непредвиденные исключения перехватываются глобально.
Так внешний клиент всегда получает конверт `{status:"error", error:{code,message}}`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from monitoring_shared import ERROR_HTTP_STATUS, ErrorCode, error


def error_response(code: ErrorCode, message: str) -> JSONResponse:
    """Собрать JSONResponse-конверт ошибки со статусом из ERROR_HTTP_STATUS."""
    return JSONResponse(status_code=ERROR_HTTP_STATUS[code], content=error(code, message))


def api_error(code: ErrorCode, message: str) -> HTTPException:
    """Доменная ошибка: HTTPException, несущий код и сообщение конверта.

    Использование: `raise api_error(ErrorCode.TASK_NOT_FOUND, "Задание не найдено")`.
    """
    return HTTPException(
        status_code=ERROR_HTTP_STATUS[code],
        detail={"code": str(code), "message": message},
    )


# Коды для «голых» фреймворковых HTTPException (без нашего detail).
# Доменные коды 404 (TASK_/EVENT_NOT_FOUND) приходят только через detail-словарь,
# поэтому здесь по статусу даём фреймворковые коды, а не доменные.
_FRAMEWORK_STATUS_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: str(ErrorCode.VALIDATION_ERROR),
    500: str(ErrorCode.INTERNAL),
    501: str(ErrorCode.NOT_IMPLEMENTED),
}


def _http_status_to_code(status_code: int) -> str:
    """Подобрать код ошибки для «голого» HTTPException без нашего detail."""
    return _FRAMEWORK_STATUS_CODE.get(status_code, str(ErrorCode.INTERNAL))


def register_error_handlers(app: FastAPI) -> None:
    """Зарегистрировать глобальные обработчики ошибок на приложении."""

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        """Невалидное тело запроса → 422 VALIDATION_ERROR."""
        return error_response(ErrorCode.VALIDATION_ERROR, "Тело запроса не прошло валидацию")

    @app.exception_handler(StarletteHTTPException)
    async def on_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """HTTPException → конверт. Доменный код берём из detail, иначе — по статусу."""
        detail: Any = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            content = error(detail["code"], detail.get("message", ""))
        else:
            content = error(_http_status_to_code(exc.status_code), str(detail))
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def on_unhandled(_request: Request, _exc: Exception) -> JSONResponse:
        """Непредвиденная ошибка → 500 INTERNAL (без утечки деталей наружу)."""
        return error_response(ErrorCode.INTERNAL, "Внутренняя ошибка сервиса")
