"""Конфигурация api-gateway из переменных окружения (.env)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Допустимые роли (по возрастанию прав). admin наследует права operator.
VALID_ROLES = ("operator", "admin")


def parse_api_keys(raw: str | None) -> dict[str, str]:
    """Разобрать API_KEYS вида «ключ:роль,ключ:роль» в карту ключ→роль.

    Устойчиво к мусору: пустые элементы, отсутствие роли и неизвестные роли
    пропускаются с предупреждением (старт не падает из-за опечатки в .env).
    """
    result: dict[str, str] = {}
    if not raw:
        return result
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, role = item.partition(":")
        key = key.strip()
        role = role.strip().lower()
        if not sep or not key or role not in VALID_ROLES:
            logger.warning("API_KEYS: пропущен некорректный элемент (ожидается «ключ:роль»)")
            continue
        result[key] = role
    return result


@dataclass(frozen=True)
class Settings:
    """Параметры внешнего шлюза."""

    # Базовый URL внутреннего log-service (источник событий).
    log_service_url: str
    # Legacy-ключ администратора (X-API-Key). Совместимость: API_KEY = роль admin.
    api_key: str | None
    # СТЫК-АУРА (v2): фичефлаг интеграции; в v1 всегда False (разъёмы отдают 501).
    aura_integration_enabled: bool
    # Базовый URL медиа-шлюза go2rtc (для кадра-превью камеры в GUI разметки ROI).
    go2rtc_url: str = "http://media-gateway:1984"
    # Каталог артефактов-доказательств (общий том со воркером). Из него отдаются
    # стоп-кадры/overlay в Grafana и сюда же кладутся снимки браузерного анализа.
    artifacts_dir: str = "/data/artifacts"
    # Ключи per-user с ролями (API_KEYS=ключ:роль,...). Роли: operator|admin (#291).
    api_keys: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        """Собрать настройки из окружения (значения по умолчанию — как в compose)."""
        return cls(
            log_service_url=os.getenv("LOG_SERVICE_URL", "http://log-service:8000"),
            api_key=os.getenv("API_KEY") or None,
            aura_integration_enabled=os.getenv("AURA_INTEGRATION_ENABLED", "false").lower()
            == "true",
            go2rtc_url=os.getenv("GO2RTC_URL", "http://media-gateway:1984"),
            artifacts_dir=os.getenv("ARTIFACTS_DIR", "/data/artifacts"),
            api_keys=parse_api_keys(os.getenv("API_KEYS")),
        )

    def principals(self) -> dict[str, str]:
        """Карта всех валидных ключей → роль (API_KEY добавляется как admin)."""
        keys = dict(self.api_keys)
        if self.api_key:
            keys[self.api_key] = "admin"  # совместимость: legacy-ключ = админ
        return keys

    def auth_enabled(self) -> bool:
        """Включена ли проверка ключа (задан хотя бы один ключ)."""
        return bool(self.api_key or self.api_keys)
