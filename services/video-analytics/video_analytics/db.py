"""Подключение video-analytics к БД."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine


def database_url() -> str:
    """Собрать URL подключения к БД из окружения."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "monitoring")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "monitoring")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def build_engine(url: str | None = None) -> Engine:
    """Создать engine SQLAlchemy."""
    return create_engine(url or database_url())
