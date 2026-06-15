"""Лицензирование: демо-лимиты и тарифы по офлайн-ключу (#335, docs/14).

Демо без ключа ограничено (1 помещение, 1 камера, 1 узел). Расширение — по
лицензионному ключу: строка `payload.signature` (base64url), где payload —
JSON с тарифом, лимитами и сроком, а signature — подпись Ed25519 над байтами
payload приватным ключом вендора. Продукт проверяет подпись зашитым публичным
ключом — офлайн, без сервера лицензий; подделать лимиты/срок нельзя.

Проверка лицензии не должна ронять API: любой сбой (нет ключа, битый формат,
плохая подпись, истёк срок) → молчаливый откат к демо-лимитам (статус отражает
причину для GUI). Приватный ключ в репозиторий не попадает; публичный —
константа ниже (заменяется своим через scripts/gen_license_keypair.py).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

# Сущности, на которые действует лимит тарифа.
LIMITED = ("rooms", "cameras", "nodes")

# Демо-тариф (без валидного ключа): по одному на каждую сущность.
DEMO_LIMITS: dict[str, int | None] = {"rooms": 1, "cameras": 1, "nodes": 1}

# Публичный ключ вендора для проверки подписи лицензий (Ed25519, hex 32 байта).
# Это БОЕВОЙ публичный ключ: ему соответствует приватный ключ вендора, которым
# подписываются лицензии (scripts/gen_license.py). Приватный ключ хранится ВНЕ
# репозитория (см. licenses/ в .gitignore). Ротация ключа = новая пара
# (scripts/gen_license_keypair.py) + замена этой константы во всех установках.
EMBEDDED_PUBLIC_KEY_HEX = "fcf818d38101245cd17bb9082e6152e08c66420b131a27cd1ddf441d63c75d2c"


@dataclass(frozen=True)
class LicenseInfo:
    """Результат вычисления лицензии: тариф, лимиты и статус для GUI."""

    status: str  # demo | active | expired | invalid
    tier: str  # demo | <из ключа>
    limits: dict[str, int | None]  # роль → лимит (None = без ограничения)
    customer: str | None = None
    expires: str | None = None  # ISO-дата срока действия (если есть)


def _demo(
    status: str = "demo", customer: str | None = None, expires: str | None = None
) -> LicenseInfo:
    """Демо-лицензия (используется и как откат при невалидном/истёкшем ключе)."""
    return LicenseInfo(
        status=status, tier="demo", limits=dict(DEMO_LIMITS), customer=customer, expires=expires
    )


def _b64url_decode(value: str) -> bytes:
    """Декодировать base64url с восстановлением паддинга."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def evaluate_license(
    key: str | None, today: date, *, public_key_hex: str | None = None
) -> LicenseInfo:
    """Вычислить действующую лицензию из ключа (или демо при любой проблеме).

    `today` — текущая дата (UTC) для проверки срока; передаётся явно для тестов.
    `public_key_hex` — публичный ключ вендора; по умолчанию берётся зашитый
    EMBEDDED_PUBLIC_KEY_HEX в момент вызова (тесты могут подменить константу).
    Возвращает LicenseInfo: при отсутствии/невалидности ключа — демо-лимиты, при
    истечении — демо-лимиты со статусом `expired` (и данными ключа для GUI).
    """
    if not key or not key.strip():
        return _demo()

    pub_hex = public_key_hex if public_key_hex is not None else EMBEDDED_PUBLIC_KEY_HEX

    try:
        payload_b64, sig_b64 = key.strip().split(".", 1)
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error):
        logger.warning("Лицензия: неверный формат ключа — демо-режим")
        return _demo(status="invalid")

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(signature, payload_bytes)
    except (InvalidSignature, ValueError):
        logger.warning("Лицензия: подпись не прошла проверку — демо-режим")
        return _demo(status="invalid")

    try:
        data = json.loads(payload_bytes)
        tier = str(data.get("tier", "pro"))
        customer = data.get("customer")
        expires = data.get("expires")
        limits: dict[str, int | None] = {}
        for role in LIMITED:
            raw = data.get(f"max_{role}")
            # null/отсутствие = без ограничения; число = лимит.
            limits[role] = None if raw is None else int(raw)
    except (ValueError, TypeError):
        logger.warning("Лицензия: повреждён payload — демо-режим")
        return _demo(status="invalid")

    # Срок действия (подписка): после expires — мягкий откат к демо.
    if expires:
        try:
            if date.fromisoformat(str(expires)) < today:
                logger.info("Лицензия клиента «%s» истекла %s — демо-режим", customer, expires)
                return _demo(status="expired", customer=customer, expires=expires)
        except ValueError:
            return _demo(status="invalid")

    return LicenseInfo(
        status="active", tier=tier, limits=limits, customer=customer, expires=expires
    )


def limit_reached(info: LicenseInfo, role: str, current_count: int) -> bool:
    """True, если заведение ещё одной сущности `role` превысит лимит тарифа."""
    limit = info.limits.get(role)
    if limit is None:  # без ограничения
        return False
    return current_count >= limit


def today_utc(now: datetime) -> date:
    """Дата UTC из момента времени (для проверки срока лицензии)."""
    return now.date()
