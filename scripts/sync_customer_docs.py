"""Синхронизация схем в пакете документации для заказчика.

Схемы в `docs/customer/diagrams/` — это копии рендеров из `docs/diagrams/`
(источник истины). Скрипт держит копии в актуальном состоянии и умеет проверять
рассинхрон в CI.

Запуск:
    python scripts/sync_customer_docs.py            # синхронизировать (скопировать)
    python scripts/sync_customer_docs.py --check     # только проверить (для CI)

В режиме --check скрипт завершается с кодом 1, если копии отличаются от
источников (например, схему обновили в docs/diagrams/, а в пакет не перенесли).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Корень репозитория — на уровень выше каталога scripts/.
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "docs" / "diagrams"
TARGET_DIR = REPO_ROOT / "docs" / "customer" / "diagrams"

# Схемы, входящие в пакет заказчика (встроены в РУКОВОДСТВО_ЗАКАЗЧИКА.md).
CUSTOMER_DIAGRAMS = (
    "01_topology.svg",
    "02_network.svg",
    "03_api_collaboration.svg",
    "04_task_lifecycle.svg",
    "05_event_flow.svg",
    "06_components.svg",
    "07a_sensors.svg",
    "07b_analytics.svg",
    "07c_rest.svg",
    "07d_startup.svg",
)


def out_of_sync() -> list[str]:
    """Вернуть имена схем, чьи копии отсутствуют или отличаются от источника."""
    stale: list[str] = []
    for name in CUSTOMER_DIAGRAMS:
        source = SOURCE_DIR / name
        target = TARGET_DIR / name
        if not source.is_file():
            raise FileNotFoundError(f"Нет исходной схемы: {source}")
        if not target.is_file() or target.read_bytes() != source.read_bytes():
            stale.append(name)
    return stale


def sync() -> list[str]:
    """Скопировать все схемы пакета из источника; вернуть список обновлённых."""
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    updated = out_of_sync()
    for name in updated:
        (TARGET_DIR / name).write_bytes((SOURCE_DIR / name).read_bytes())
    return updated


def main() -> int:
    """CLI: синхронизировать копии или проверить их актуальность (--check)."""
    parser = argparse.ArgumentParser(description="Синхронизация схем пакета заказчика")
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверка (выход 1 при рассинхроне), без копирования",
    )
    args = parser.parse_args()

    stale = out_of_sync()
    if args.check:
        if stale:
            print("Копии схем устарели, выполните python scripts/sync_customer_docs.py:")
            for name in stale:
                print(f"  - {name}")
            return 1
        print("Схемы пакета заказчика синхронизированы.")
        return 0

    updated = sync()
    print(f"Синхронизировано схем: {len(updated)} из {len(CUSTOMER_DIAGRAMS)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
