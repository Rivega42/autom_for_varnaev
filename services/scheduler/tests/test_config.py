"""Конфигурация планировщика из окружения (#331 — таймаут пробы живости)."""

from __future__ import annotations

import pytest
from scheduler.camera_store import Go2rtcCameraProber
from scheduler.config import Settings


def test_camera_probe_timeout_default() -> None:
    """По умолчанию таймаут пробы живости — 8 с (не короткие 3 с)."""
    assert Settings("/c/s.json", 60).camera_probe_timeout_s == 8.0


def test_camera_probe_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CAMERA_PROBE_TIMEOUT_S читается из окружения как число секунд."""
    monkeypatch.setenv("CAMERA_PROBE_TIMEOUT_S", "12.5")
    assert Settings.from_env().camera_probe_timeout_s == 12.5


def test_prober_uses_configured_timeout() -> None:
    """Go2rtcCameraProber применяет переданный таймаут (а не зашитые 3 с)."""
    prober = Go2rtcCameraProber("http://media-gateway:1984", timeout=8.0)
    assert prober._timeout == 8.0
