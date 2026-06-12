"""Проверка мягкой остановки (#206): Event взводится по SIGTERM/SIGINT."""

from __future__ import annotations

import signal
from collections.abc import Iterator

import pytest

from monitoring_shared import install_stop_event


@pytest.fixture
def _restore_handlers() -> Iterator[None]:
    """Вернуть исходные обработчики сигналов после теста (не мешаем pytest)."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


@pytest.mark.usefixtures("_restore_handlers")
def test_event_set_on_sigterm() -> None:
    """Обработчик SIGTERM взводит Event (вызываем обработчик напрямую)."""
    stop = install_stop_event()
    assert not stop.is_set()
    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)
    handler(signal.SIGTERM, None)
    assert stop.is_set()


@pytest.mark.usefixtures("_restore_handlers")
def test_event_set_on_sigint() -> None:
    """SIGINT (Ctrl+C) тоже ведёт к мягкой остановке."""
    stop = install_stop_event()
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)
    handler(signal.SIGINT, None)
    assert stop.is_set()
