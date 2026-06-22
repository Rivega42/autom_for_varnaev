"""Аутентификация и роли по X-API-Key (docs/03_API_CONTRACT.md §1, #291).

Ключи задаются в `.env`: `API_KEYS=ключ:роль,ключ:роль` (роли operator|admin);
legacy `API_KEY` трактуется как роль admin (совместимость). Роль `operator`
может читать и подтверждать события (ack); `admin` — ещё и настраивать
(камеры/пороги/расписания/правила/справочники).

Если ключи не заданы вовсе (dev/тесты) — проверка отключена, запрос считается
admin. Внутренние вызовы в v1 доверяются по сети `internal`, `/health` открыт.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Header, HTTPException, Query

from api_gateway.config import Settings

logger = logging.getLogger(__name__)

# Ранги ролей (больше — больше прав). admin покрывает права operator.
_ROLE_RANK = {"operator": 1, "admin": 2}


@dataclass(frozen=True)
class Principal:
    """Кто выполняет запрос (роль; имя пользователя при ключах в .env недоступно)."""

    role: str


def _resolve_role(settings: Settings, *candidates: str | None) -> str | None:
    """Вернуть роль по первому подходящему ключу из переданных кандидатов.

    Если проверка отключена (ключи не настроены) — admin (fail-open для dev/тестов).
    Сравнение ключей — постоянным временем (без тайминг-оракула).
    """
    if not settings.auth_enabled():
        return "admin"
    principals = settings.principals()
    for candidate in candidates:
        if candidate is None:
            continue
        for key, role in principals.items():
            # Сравниваем в БАЙТАХ, а не в str. `hmac.compare_digest` на str требует
            # ASCII и бросает «comparing strings with non-ASCII characters is not
            # supported»; под Nuitka это срабатывает даже на ASCII-ключах (C-проверка
            # PyUnicode_IS_ASCII не признаёт скомпилированную строку компактно-ASCII).
            # На bytes такого ограничения нет, сравнение остаётся постоянным по времени.
            if secrets.compare_digest(candidate.encode("utf-8"), key.encode("utf-8")):
                return role
    return None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "UNAUTHORIZED", "message": "Неверный или отсутствующий API-ключ"},
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"code": "FORBIDDEN", "message": "Недостаточно прав (требуется роль admin)"},
    )


def make_require_role(settings: Settings, required: str) -> Callable[..., Principal]:
    """Собрать зависимость, требующую роль не ниже `required` (X-API-Key)."""
    if not settings.auth_enabled():
        logger.warning(
            "Ключи API не заданы — проверка X-API-Key ОТКЛЮЧЕНА (только для локальной "
            "разработки/тестов; в проде задайте API_KEY и/или API_KEYS)"
        )
    need = _ROLE_RANK[required]

    def require_role(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> Principal:
        """Пропустить запрос с ролью не ниже требуемой; иначе 401/403."""
        role = _resolve_role(settings, x_api_key)
        if role is None:
            raise _unauthorized()
        if _ROLE_RANK[role] < need:
            raise _forbidden()
        return Principal(role=role)

    return require_role


def make_require_api_key_media(settings: Settings) -> Callable[..., Principal]:
    """Зависимость проверки ключа для МЕДИА-эндпойнтов (кадр/видеопоток).

    Принимает ключ из заголовка X-API-Key ИЛИ из query-параметра `api_key` —
    тег <img>/видео в браузере не умеет слать заголовки. Ключ в URL — осознанный
    компромисс для внутреннего GUI (LAN): медиа-эндпойнты наружу не публикуются.
    Достаточно любой валидной роли (operator).
    """

    def require_api_key_media(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        api_key: str | None = Query(default=None),
    ) -> Principal:
        """Пропустить запрос с верным ключом из заголовка или query (или если ключ не настроен)."""
        role = _resolve_role(settings, x_api_key, api_key)
        if role is None:
            raise _unauthorized()
        return Principal(role=role)

    return require_api_key_media
