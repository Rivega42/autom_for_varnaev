"""Точка входа video-analytics: мягкая остановка и диагностика модели (#206)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine
from video_analytics import main as main_mod
from video_analytics.config import Settings
from video_analytics.detector import PoseDetector
from video_analytics.event_sink import EventSink
from video_analytics.worker import SourceFactory

_SETTINGS = Settings(
    log_service_url="http://log-service:8000",
    artifacts_dir="/tmp/artifacts",
    fps=5,
    artifacts_retention_days=0,
)


def test_run_forever_stops_on_signal() -> None:
    """Взведённый should_stop завершает цикл до обращения к БД и детектору."""
    # Заглушки не вызываются: проверка остановки идёт первой в итерации.
    main_mod.run_forever(
        cast(Engine, object()),
        _SETTINGS,
        detector=cast(PoseDetector, object()),
        sink=cast(EventSink, object()),
        source_factory=cast(SourceFactory, object()),
        should_stop=lambda: True,
    )


def test_main_fails_clearly_without_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Нет файла модели → выход с кодом 1 и понятным сообщением (не трейс MediaPipe)."""
    monkeypatch.setenv("ANALYTICS_MODEL_PATH", str(tmp_path / "missing.task"))
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1
    assert "Файл модели MediaPipe не найден" in caplog.text
    assert "fetch_model.sh" in caplog.text
