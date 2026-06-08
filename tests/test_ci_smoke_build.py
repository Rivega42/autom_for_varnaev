"""Проверка CI smoke-build образов (E0.11): сборка всех сервисов без публикации."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_CI = REPO_ROOT / ".github/workflows/ci.yml"

_SERVICES = {
    "api-gateway",
    "log-service",
    "ingest-sensors",
    "scheduler",
    "video-analytics",
    "demo-sensors",
}


def _ci() -> dict[str, Any]:
    data = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _docker_build_job() -> dict[str, Any]:
    job = _ci()["jobs"]["docker-build"]
    assert isinstance(job, dict)
    return job


def test_docker_build_job_present() -> None:
    """В CI есть отдельный job сборки Docker-образов."""
    assert "docker-build" in _ci()["jobs"]


def test_builds_all_services() -> None:
    """Матрица сборки покрывает все сервисы с Dockerfile (services/<svc>/Dockerfile)."""
    services = set(_docker_build_job()["strategy"]["matrix"]["service"])
    assert services == _SERVICES


def test_build_without_push_with_cache() -> None:
    """Сборка без публикации (push: false) и с кэшем слоёв."""
    steps = _docker_build_job()["steps"]
    build = next(s for s in steps if str(s.get("uses", "")).startswith("docker/build-push-action"))
    assert build["with"]["push"] is False
    assert "cache-from" in build["with"]
