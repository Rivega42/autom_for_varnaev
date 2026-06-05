"""api-gateway: единственный внешний вход контура (эпик E6).

Рабочие эндпойнты v1 (`/api/v1/...`) и разъёмы АУРА (`/api/v1/integration/...`,
заглушены в v1 за фичефлагом `aura_integration_enabled`). Все ответы — в едином
конверте из `monitoring_shared` (docs/03_API_CONTRACT.md).
"""

from api_gateway.app import create_app

__all__ = ["create_app"]
