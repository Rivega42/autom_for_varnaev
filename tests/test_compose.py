"""Smoke-тест docker-compose: валидность YAML и наличие сервиса grafana.

Проверяет, что Grafana поднята в compose согласно docs/02_NETWORK.md §3
(сеть internal, публикация порта наружу).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict[str, Any]:
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert isinstance(data, dict)
    return data


def test_compose_is_valid_yaml() -> None:
    """docker-compose.yml парсится и содержит секции services/networks/volumes."""
    compose = _compose()
    assert "services" in compose
    assert "networks" in compose
    assert "volumes" in compose


def test_grafana_service_present() -> None:
    """Сервис grafana — на сети internal, публикует порт, монтирует provisioning."""
    grafana = _compose()["services"].get("grafana")
    assert grafana is not None, "Сервис grafana отсутствует в compose"
    assert "internal" in grafana["networks"]
    assert any("3000" in str(p) for p in grafana["ports"]), "Порт дашборда не опубликован"
    mounts = " ".join(grafana["volumes"])
    assert "provisioning" in mounts
    assert "dashboards" in mounts


def test_grafana_volume_declared() -> None:
    """Том grafana_data объявлен в секции volumes."""
    assert "grafana_data" in _compose()["volumes"]


# ── Финальный compose (E9.6): прикладные сервисы ──

# Внутренние сервисы (наружу не публикуются, только сеть internal).
_INTERNAL_ONLY = ("log-service", "ingest-sensors", "scheduler", "video-analytics")


def test_all_app_services_present_with_build() -> None:
    """Все пять наших сервисов присутствуют и собираются из своих Dockerfile."""
    services = _compose()["services"]
    for name in ("api-gateway", "log-service", "ingest-sensors", "scheduler", "video-analytics"):
        assert name in services, f"Сервис {name} отсутствует в compose"
        build = services[name]["build"]
        assert build["dockerfile"] == f"services/{name}/Dockerfile"
        assert build["context"] == "."


def test_internal_services_not_published() -> None:
    """Внутренние сервисы не публикуют портов наружу и сидят только в internal."""
    services = _compose()["services"]
    for name in _INTERNAL_ONLY:
        svc = services[name]
        assert "ports" not in svc, f"{name} не должен публиковать порт наружу"
        assert svc["networks"] == ["internal"]


def test_api_gateway_bridges_networks_and_published() -> None:
    """api-gateway — в internal+integration+edge и единственный с REST наружу.

    edge нужен, потому что internal объявлена с internal: true (реальная
    изоляция): публикуемый порт из чисто internal-сети не работает.
    """
    gateway = _compose()["services"]["api-gateway"]
    assert set(gateway["networks"]) == {"internal", "integration", "edge"}
    assert any("8000" in str(p) for p in gateway["ports"]), "REST-порт не опубликован"


def test_internal_network_isolated_and_edge_declared() -> None:
    """Сеть internal реально изолирована (internal: true); edge объявлена для
    публикуемых портов и доступа к LAN (mqtt, grafana, media-gateway)."""
    compose = _compose()
    assert compose["networks"]["internal"].get("internal") is True
    assert "edge" in compose["networks"]
    for name in ("mqtt-broker", "grafana", "media-gateway"):
        assert "edge" in compose["services"][name]["networks"], f"{name} без edge"


def test_video_analytics_mounts_artifacts() -> None:
    """video-analytics монтирует общий том artifacts."""
    va = _compose()["services"]["video-analytics"]
    assert any("artifacts:/data/artifacts" in v for v in va["volumes"])


# ── Применение миграций Alembic (migrate-сервис) ──

# Сервисы, которым нужна готовая схема БД до старта (зависят от migrate).
_NEEDS_SCHEMA = (
    "log-service",
    "api-gateway",
    "ingest-sensors",
    "scheduler",
    "video-analytics",
    "grafana",
)


def test_migrate_service_present() -> None:
    """Сервис migrate собирается из db/Dockerfile, в internal, ждёт healthy БД."""
    migrate = _compose()["services"].get("migrate")
    assert migrate is not None, "Сервис migrate отсутствует в compose"
    assert migrate["build"]["dockerfile"] == "db/Dockerfile"
    assert migrate["build"]["context"] == "."
    assert migrate["networks"] == ["internal"]
    assert migrate["depends_on"]["db"]["condition"] == "service_healthy"
    # Одноразовая задача: не перезапускается после успешного завершения.
    assert str(migrate["restart"]) == "no"


def test_schema_consumers_wait_for_migrate() -> None:
    """Сервисы, читающие/пишущие таблицы, стартуют после успешных миграций."""
    services = _compose()["services"]
    for name in _NEEDS_SCHEMA:
        depends = services[name]["depends_on"]
        assert "migrate" in depends, f"{name} должен зависеть от migrate"
        assert depends["migrate"]["condition"] == "service_completed_successfully"


# ── Полнота .env.example относительно docker-compose ──


def _compose_env_vars() -> set[str]:
    """Имена переменных, на которые ссылается compose через ${VAR...}."""
    lines = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    # Отбрасываем комментарии (в них встречаются литералы вроде «через ${VAR}»).
    body = "\n".join(line.split("#", 1)[0] for line in lines)
    # ${VAR}, ${VAR:-default}, ${VAR:?msg} — берём только имя.
    return set(re.findall(r"\$\{([A-Z0-9_]+)[}:]", body))


def _env_example_keys() -> set[str]:
    """Ключи, объявленные в .env.example (строки вида KEY=...)."""
    keys: set[str] = set()
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_documents_all_compose_vars() -> None:
    """Каждая переменная из docker-compose описана в .env.example (E0.3)."""
    missing = _compose_env_vars() - _env_example_keys()
    assert not missing, f".env.example не содержит переменных compose: {sorted(missing)}"


# ── Профили dev/release (E9.7) ──


def test_dev_services_have_no_profile() -> None:
    """dev-сервисы работают по умолчанию (без profiles)."""
    services = _compose()["services"]
    for name in ("api-gateway", "log-service", "ingest-sensors", "scheduler", "video-analytics"):
        assert "profiles" not in services[name], f"{name} не должен иметь профиль (он дефолтный)"


def test_release_variants_under_release_profile() -> None:
    """Release-варианты — под профилем release и собираются из Dockerfile.release."""
    services = _compose()["services"]
    for name, df in (
        ("api-gateway-release", "services/api-gateway/Dockerfile.release"),
        ("video-analytics-release", "services/video-analytics/Dockerfile.release"),
    ):
        svc = services[name]
        assert svc["profiles"] == ["release"], f"{name} должен быть под профилем release"
        assert svc["build"]["dockerfile"] == df
