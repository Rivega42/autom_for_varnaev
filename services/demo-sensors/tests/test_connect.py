"""Тесты подключения demo-sensors к MQTT с повтором."""

from __future__ import annotations

import pytest
from demo_sensors.main import connect_with_retry


class _FlakyClient:
    """Фейковый MQTT-клиент: падает первые `fail_times` попыток, затем успех."""

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.attempts = 0

    def connect(self, host: str, port: int) -> None:
        self.attempts += 1
        if self.attempts <= self._fail_times:
            raise ConnectionRefusedError("брокер ещё не готов")


def test_connect_retries_until_success() -> None:
    """Подключение повторяется, пока брокер не примет соединение."""
    client = _FlakyClient(fail_times=3)
    delays: list[float] = []
    connect_with_retry(client, "mqtt", 1883, sleep=delays.append)  # type: ignore[arg-type]
    assert client.attempts == 4  # 3 неудачи + 1 успех
    # Экспоненциальная задержка между попытками: 1, 2, 4.
    assert delays == [1, 2, 4]


def test_connect_succeeds_first_try() -> None:
    """При доступном брокере подключение без задержек."""
    client = _FlakyClient(fail_times=0)
    delays: list[float] = []
    connect_with_retry(client, "mqtt", 1883, sleep=delays.append)  # type: ignore[arg-type]
    assert client.attempts == 1
    assert delays == []


def test_connect_delay_capped() -> None:
    """Задержка не превышает max_delay."""
    client = _FlakyClient(fail_times=6)
    delays: list[float] = []
    connect_with_retry(client, "mqtt", 1883, max_delay=4, sleep=delays.append)  # type: ignore[arg-type]
    assert max(delays) == 4
    assert delays == [1, 2, 4, 4, 4, 4]


def test_connect_propagates_non_oserror() -> None:
    """Не-сетевые ошибки не глотаются (повтор только для OSError)."""

    class _Boom:
        def connect(self, host: str, port: int) -> None:
            raise ValueError("конфигурационная ошибка")

    with pytest.raises(ValueError):
        connect_with_retry(_Boom(), "mqtt", 1883, sleep=lambda _d: None)  # type: ignore[arg-type]
