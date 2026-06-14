"""Доступ к app_config: ключ-значение настроек контура, редактируемых из GUI (#335)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine, delete, insert, select, update

from api_gateway.tables import app_config


def get_config(engine: Engine, key: str) -> str | None:
    """Значение настройки по ключу или None."""
    stmt = select(app_config.c.value).where(app_config.c.key == key)
    with engine.connect() as conn:
        row = conn.execute(stmt).first()
    return row[0] if row is not None else None


def set_config(engine: Engine, key: str, value: str, now: datetime) -> None:
    """Установить значение настройки по ключу (вставка или обновление)."""
    # Портируемый UPSERT без диалект-специфичного ON CONFLICT: сперва UPDATE,
    # если строки не было — INSERT. Работает одинаково в SQLite (тесты) и
    # PostgreSQL (прод); запись настроек редкая, гонок здесь нет.
    with engine.begin() as conn:
        updated = conn.execute(
            update(app_config).where(app_config.c.key == key).values(value=value, updated_at=now)
        )
        if updated.rowcount == 0:
            conn.execute(insert(app_config).values(key=key, value=value, updated_at=now))


def clear_config(engine: Engine, key: str) -> None:
    """Удалить настройку (вернуться к значению по умолчанию/env)."""
    with engine.begin() as conn:
        conn.execute(delete(app_config).where(app_config.c.key == key))
