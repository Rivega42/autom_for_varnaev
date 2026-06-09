"""Аутентификация по X-API-Key (docs/03_API_CONTRACT.md §1).

Публичные эндпойнты и разъёмы `/integration/*` защищены ключом из `.env`.
Внутренние вызовы в v1 доверяются по сети `internal`, а `/health` открыт.
Если ключ в конфиге не задан (dev/тесты) — проверка отключена.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

from fastapi import Header, HTTPException, Query

from api_gateway.config import Settings

logger = logging.getLogger(__name__)


def _key_ok(received: str | None, expected: str) -> bool:
    """Сравнить ключи за постоянное время (без тайминг-оракула)."""
    return received is not None and secrets.compare_digest(received, expected)


def make_require_api_key_media(settings: Settings) -> Callable[[str | None, str | None], None]:
    """Зависимость проверки ключа для МЕДИА-эндпойнтов (кадр/видеопоток).

    Принимает ключ из заголовка X-API-Key ИЛИ из query-параметра `api_key` —
    тег <img>/видео в браузере не умеет слать заголовки. Ключ в URL — осознанный
    компромисс для внутреннего GUI (LAN): медиа-эндпойнты наружу за пределы
    контура не публикуются, а сам GUI уже работает с ключом.
    """

    def require_api_key_media(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        api_key: str | None = Query(default=None),
    ) -> None:
        """Пропустить запрос с верным ключом из заголовка или query (или если ключ не настроен)."""
        if settings.api_key is None:
            return
        if _key_ok(x_api_key, settings.api_key) or _key_ok(api_key, settings.api_key):
            return
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Неверный или отсутствующий API-ключ"},
        )

    return require_api_key_media


def make_require_api_key(settings: Settings) -> Callable[[str | None], None]:
    """Собрать FastAPI-зависимость проверки X-API-Key для данного конфига."""

    if settings.api_key is None:
        # Fail-open только для dev/тестов. В compose API_KEY обязателен.
        logger.warning(
            "API_KEY не задан — проверка X-API-Key ОТКЛЮЧЕНА (допустимо только для "
            "локальной разработки/тестов; в проде задайте API_KEY)"
        )

    def require_api_key(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> None:
        """Пропустить запрос только с верным ключом (либо если ключ не настроен)."""
        if settings.api_key is None:
            return
        if not _key_ok(x_api_key, settings.api_key):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "Неверный или отсутствующий API-ключ",
                },
            )

    return require_api_key
