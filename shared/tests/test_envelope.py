"""Проверка единого конверта ответа из monitoring_shared."""

from __future__ import annotations

from monitoring_shared import (
    ERROR_HTTP_STATUS,
    Envelope,
    ErrorCode,
    error,
    ok,
)


def test_ok_envelope_shape() -> None:
    """ok() даёт конверт со status=ok, заполненным data и пустой ошибкой."""
    env = ok({"x": 1})
    assert env["status"] == "ok"
    assert env["data"] == {"x": 1}
    assert env["error"] is None
    assert env["ts"].endswith("+00:00") or env["ts"].endswith("Z")


def test_error_envelope_shape() -> None:
    """error() даёт конверт со status=error и телом ошибки."""
    env = error(ErrorCode.TASK_NOT_FOUND, "Задание не найдено")
    assert env["status"] == "error"
    assert env["data"] is None
    assert env["error"] == {"code": "TASK_NOT_FOUND", "message": "Задание не найдено"}


def test_envelope_model_validates() -> None:
    """Конверт проходит валидацию модели Envelope."""
    Envelope.model_validate(ok({"ok": True}))
    Envelope.model_validate(error(ErrorCode.INTERNAL, "сбой"))


def test_all_error_codes_have_http_status() -> None:
    """Каждому коду ошибки сопоставлен HTTP-статус."""
    for code in ErrorCode:
        assert code in ERROR_HTTP_STATUS
    assert ERROR_HTTP_STATUS[ErrorCode.NOT_IMPLEMENTED] == 501
