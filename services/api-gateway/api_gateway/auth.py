"""Аутентификация по X-API-Key (docs/03_API_CONTRACT.md §1).

Публичные эндпойнты и разъёмы `/integration/*` защищены ключом из `.env`.
Внутренние вызовы в v1 доверяются по сети `internal`, а `/health` открыт.
Если ключ в конфиге не задан (dev/тесты) — проверка отключена.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Header, HTTPException

from api_gateway.config import Settings

logger = logging.getLogger(__name__)


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
        if x_api_key != settings.api_key:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "Неверный или отсутствующий API-ключ",
                },
            )

    return require_api_key
