"""Разбор MQTT-сообщения (топик + payload) в модель Reading.

Контракт топиков/payload — docs/08_MQTT_CONTRACT.md. Некорректные сообщения
не валят воркер: функция логирует проблему и возвращает None.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from monitoring_shared import Metric, Reading

logger = logging.getLogger(__name__)

# Резолвер помещения по узлу: node_id -> room_id | None (если узел неизвестен).
RoomResolver = Callable[[str], str | None]


def _parse_ts(raw: Any) -> datetime:
    """Разобрать ISO-8601 ts или вернуть текущее время (UTC), если ts нет/битый.

    Время без зоны нормируется к UTC: контракт MQTT задаёт UTC (суффикс `Z`), а
    БД хранит timestamptz — naive-значение привело бы к смещению/ошибке.
    """
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            logger.warning("Некорректный ts в payload: %r — беру время приёма", raw)
        else:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def parse_message(topic: str, payload: bytes, resolve_room: RoomResolver) -> Reading | None:
    """Собрать Reading из топика `<prefix>/<node_id>/<metric>` и JSON-payload.

    Возвращает None (с логом) при нераспознанной метрике, битом JSON,
    отсутствии value/unit или неизвестном узле.
    """
    parts = topic.split("/")
    if len(parts) < 3:
        logger.warning("Неожиданный формат топика: %s", topic)
        return None
    node_id, metric_raw = parts[-2], parts[-1]

    try:
        metric = Metric(metric_raw)
    except ValueError:
        logger.warning("Нераспознанная метрика в топике %s: %s", topic, metric_raw)
        return None

    try:
        parsed: Any = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Битый JSON в топике %s", topic)
        return None
    if not isinstance(parsed, dict):
        logger.warning("Payload не объект JSON в топике %s", topic)
        return None

    value = parsed.get("value")
    unit = parsed.get("unit")
    if value is None or unit is None:
        logger.warning("Нет value/unit в payload топика %s", topic)
        return None

    room_id = resolve_room(node_id)
    if room_id is None:
        logger.warning("Неизвестный узел %s (нет в справочнике) — пропуск", node_id)
        return None

    try:
        return Reading(
            ts=_parse_ts(parsed.get("ts")),
            node_id=node_id,
            room_id=room_id,
            metric=metric,
            value=float(value),
            unit=str(unit),
        )
    except (ValidationError, ValueError, TypeError):
        logger.warning("Не удалось собрать Reading из топика %s", topic)
        return None
