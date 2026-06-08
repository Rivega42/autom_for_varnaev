"""Страж синхронности пакета документации для заказчика.

Схемы в docs/customer/diagrams/ должны совпадать с источниками в docs/diagrams/.
Тест падает, если исходную схему обновили, а копию в пакет не перенесли — это
напоминание прогнать scripts/sync_customer_docs.py.
"""

from __future__ import annotations

from pathlib import Path

from sync_customer_docs import CUSTOMER_DIAGRAMS, TARGET_DIR, out_of_sync

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_customer_diagrams_in_sync() -> None:
    """Все схемы пакета заказчика синхронизированы с docs/diagrams/."""
    stale = out_of_sync()
    assert not stale, (
        f"Копии схем устарели: {stale}. Запустите python scripts/sync_customer_docs.py"
    )


def test_embedded_diagrams_are_packaged() -> None:
    """Каждая схема, встроенная в руководство, входит в список синхронизации."""
    guide = (REPO_ROOT / "docs/customer/РУКОВОДСТВО_ЗАКАЗЧИКА.md").read_text(encoding="utf-8")
    for name in CUSTOMER_DIAGRAMS:
        assert f"diagrams/{name}" in guide, f"Схема {name} не встроена в руководство"
        assert (TARGET_DIR / name).is_file(), f"Нет копии схемы {name} в пакете"
