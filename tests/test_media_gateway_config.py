"""Конфиг медиа-шлюза go2rtc: секреты камер не попадают в репозиторий.

Реальный go2rtc.yaml (RTSP-URL с логином/паролем камер) — в .gitignore;
в репозитории — только go2rtc.yaml.example с плейсхолдерами (CLAUDE.md §5,
по образцу db/seeds/object.yaml).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "media-gateway" / "go2rtc.yaml.example"


def _example() -> dict[str, Any]:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_example_is_valid_yaml_with_streams() -> None:
    """Пример парсится, слушает API-порт и описывает хотя бы один поток."""
    cfg = _example()
    assert cfg["api"]["listen"] == ":1984"
    streams = cfg["streams"]
    assert isinstance(streams, dict) and streams, "В примере нет ни одного потока"


def test_example_streams_have_mjpeg_transcode() -> None:
    """Каждый поток примера: основной RTSP-источник + MJPEG-транскод для GUI."""
    for name, sources in _example()["streams"].items():
        assert isinstance(sources, list), f"Поток {name}: ожидается список источников"
        assert any(str(s).startswith("rtsp://") for s in sources), f"{name}: нет RTSP-источника"
        assert f"ffmpeg:{name}#video=mjpeg" in sources, f"{name}: нет MJPEG-транскода"


def test_example_contains_only_placeholder_credentials() -> None:
    """В примере нет реальных логинов/паролей — только плейсхолдер LOGIN:PASSWORD."""
    text = EXAMPLE.read_text(encoding="utf-8")
    for user, password in re.findall(r"rtsp://([^:/@\s]+):([^@\s]+)@", text):
        assert (user, password) == ("LOGIN", "PASSWORD"), (
            f"В go2rtc.yaml.example похожие на реальные креды: {user}:***"
        )


def test_real_config_is_gitignored() -> None:
    """Реальный media-gateway/go2rtc.yaml перечислен в .gitignore."""
    lines = [
        line.strip() for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    ]
    assert "media-gateway/go2rtc.yaml" in lines


def test_compose_mounts_real_config() -> None:
    """compose монтирует именно go2rtc.yaml (создаётся из примера при развёртывании)."""
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    volumes = compose["services"]["media-gateway"]["volumes"]
    assert any("media-gateway/go2rtc.yaml:/config/go2rtc.yaml" in str(v) for v in volumes)
