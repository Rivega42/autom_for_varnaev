"""Аудит значимых действий (#292): запись в audit_log + зависимость-обёртка.

`make_audited(settings, engine, role)` возвращает FastAPI-зависимость, которая
проверяет роль (через `make_require_role`) и записывает строку аудита: кто
(роль), что (HTTP-метод), над чем (путь), когда. Вешается на изменяющие
эндпойнты. Сбой записи аудита не должен ронять сам запрос (логируем и идём
дальше) — но действие всё равно выполнится; для строгого аудита это допустимо в
v1 (журнал-best-effort, БД та же транзакция недоступна из зависимости).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import Engine, select

from api_gateway.auth import Principal, make_require_role
from api_gateway.config import Settings
from api_gateway.tables import audit_log

logger = logging.getLogger(__name__)


def write_audit(
    engine: Engine,
    *,
    actor: str,
    role: str,
    action: str,
    target: str,
    detail: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    """Записать строку аудита; ошибки логируются и не пробрасываются."""
    try:
        with engine.begin() as conn:
            conn.execute(
                audit_log.insert().values(
                    ts=now or datetime.now(UTC),
                    actor=actor,
                    role=role,
                    action=action,
                    target=target,
                    detail=detail,
                )
            )
    except Exception:
        logger.warning("Не удалось записать аудит действия %s %s", action, target, exc_info=True)


def make_audited(settings: Settings, engine: Engine, role: str) -> Callable[..., Principal]:
    """Зависимость: проверить роль не ниже `role` и записать действие в аудит."""
    require = make_require_role(settings, role)

    # Depends в значении по умолчанию — идиома FastAPI (подзависимость проверки роли).
    def audited(request: Request, principal: Principal = Depends(require)) -> Principal:  # noqa: B008
        # actor в v1 = роль (имени пользователя при ключах в .env нет, см. #292).
        write_audit(
            engine,
            actor=principal.role,
            role=principal.role,
            action=request.method,
            target=request.url.path,
        )
        return principal

    return audited


def list_audit(
    engine: Engine,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Список записей аудита (новые сверху) с фильтром по времени."""
    stmt = select(audit_log)
    if from_ts is not None:
        stmt = stmt.where(audit_log.c.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(audit_log.c.ts < to_ts)
    stmt = stmt.order_by(audit_log.c.ts.desc(), audit_log.c.id.desc()).limit(limit)
    with engine.connect() as conn:
        items = []
        for row in conn.execute(stmt).mappings():
            ts = row["ts"]
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            items.append(
                {
                    "id": row["id"],
                    "ts": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                    "actor": row["actor"],
                    "role": row["role"],
                    "action": row["action"],
                    "target": row["target"],
                    "detail": row["detail"],
                }
            )
        return items
