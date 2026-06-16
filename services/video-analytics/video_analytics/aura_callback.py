"""СТЫК-АУРА D.5: уведомление АУРА о готовности задания (#350).

Если у задания задан `callback_url`, по завершении (done/failed) наш контур шлёт
на него POST с уведомлением. **Best-effort:** отправитель не роняет воркер и не
влияет на статус задания — анализ уже завершён, уведомление вторично. Приёмник
реализует АУРА (должен вернуть 200 и обрабатывать идемпотентно по `task_id` —
возможна повторная доставка из-за ретраев).

Тело уведомления (docs/03 §4 webhook taskCompleted): `{task_id, status, artifacts}`.
Поле `events` контракта в v1 не заполняем (система хранит счётчик, а не список
id событий); детали АУРА забирает опросом задания D.2 (`GET /analysis-tasks/{id}`).

Защита от SSRF: только http(s)-URL; при заданном allowlist (env
AURA_CALLBACK_ALLOWED_HOSTS) хост должен быть в нём. По умолчанию allowlist пуст
(None) — доверяем, т.к. АУРА на том же объекте во внутренней сети integration.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


def _host_allowed(url: str, allowed_hosts: frozenset[str] | None) -> bool:
    """http(s)-URL и (если задан allowlist) хост из него — иначе блок (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if allowed_hosts is None:
        return True
    return parsed.hostname in allowed_hosts


class AuraNotifier:
    """Отправитель уведомлений о готовности задания в АУРА (D.5, best-effort)."""

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        retries: int = 2,
        allowed_hosts: frozenset[str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._retries = max(0, retries)
        self._allowed = allowed_hosts
        self._client = client or httpx.Client(timeout=timeout)

    def notify(
        self, callback_url: str, task_id: UUID, status: str, artifacts: list[str] | None = None
    ) -> bool:
        """POST уведомления на callback_url. True при 2xx; иначе False. Никогда не бросает."""
        if not _host_allowed(callback_url, self._allowed):
            logger.warning(
                "D.5: callback_url %s не разрешён (SSRF-защита) — уведомление не отправлено",
                callback_url,
            )
            return False
        notice = {"task_id": str(task_id), "status": status, "artifacts": artifacts or []}
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.post(callback_url, json=notice)
            except httpx.HTTPError as exc:
                logger.warning(
                    "D.5: ошибка отправки уведомления задания %s (попытка %d/%d): %s",
                    task_id,
                    attempt + 1,
                    self._retries + 1,
                    exc,
                )
                continue
            if resp.is_success:
                return True
            logger.warning(
                "D.5: АУРА вернула %s на уведомление задания %s (попытка %d/%d)",
                resp.status_code,
                task_id,
                attempt + 1,
                self._retries + 1,
            )
        return False
