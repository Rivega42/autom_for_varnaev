"""Контроль «тишины» узлов датчиков.

Узлы шлют показания сами; если узел молчит дольше порога `silent_min`, это
сигнал проблемы (критично для холодовой цепи). Монитор отслеживает время
последнего показания по узлу и сообщает об «онемевших» узлах однократно.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime


class SilenceMonitor:
    """Отслеживает время последнего показания по узлам и тишину дольше порога."""

    def __init__(self) -> None:
        self._last_seen: dict[str, datetime] = {}
        self._flagged: set[str] = set()

    def record(self, node_id: str, ts: datetime) -> None:
        """Зафиксировать показание узла (сбрасывает признак тишины)."""
        self._last_seen[node_id] = ts
        self._flagged.discard(node_id)

    def silent_nodes(
        self, now: datetime, silent_min: int | Callable[[str], int]
    ) -> list[tuple[str, int]]:
        """Узлы, молчащие дольше порога минут (однократно на эпизод тишины).

        `silent_min` — общий порог (int) либо функция `node_id -> минут` (порог
        зависит от помещения узла, см. docs/08). Возвращает список (node_id, прошло_минут).
        """
        threshold_for: Callable[[str], int] = (
            silent_min if callable(silent_min) else (lambda _node: silent_min)
        )
        result: list[tuple[str, int]] = []
        for node_id, last in self._last_seen.items():
            elapsed_min = (now - last).total_seconds() / 60.0
            if elapsed_min > threshold_for(node_id) and node_id not in self._flagged:
                self._flagged.add(node_id)
                result.append((node_id, int(elapsed_min)))
        return result
