"""Общие фикстуры тестов log-service."""

import pytest
from log_service.tables import metadata
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Engine:
    """In-memory SQLite с созданной таблицей events."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(eng)
    return eng
