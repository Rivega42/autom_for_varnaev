"""Демо-сид: справочники и пороги демо-стенда (только демо-режим).

Заводит помещения/узлы/камеры из db/seeds/demo.yaml (повторно используя
scripts/seed.py) и набор демо-порогов, чтобы в демо периодически срабатывали
события (порог превышения). Идемпотентно: повторный запуск не дублирует данные.

Запуск (внутри сети контура, см. docker-compose.demo.yml):
    python scripts/demo_seed.py            # dry-run: только разбор демо-конфига
    python scripts/demo_seed.py --apply    # запись справочников и порогов в БД
"""

from __future__ import annotations

import argparse
from pathlib import Path

from seed import _database_url, apply, load_config

# Демо-конфиг лежит в репозитории рядом с примером.
DEMO_CONFIG = Path(__file__).resolve().parent.parent / "db" / "seeds" / "demo.yaml"

# Демо-пороги: (room_id | None, metric, op, value, severity). None = глобальный.
# Подобраны под значения, которые публикует demo-sensors при «всплеске»:
#   влажность > 70% (всплеск node-01 → 82%) и темп. воздуха в холодильной
#   камере > 8 °C (всплеск node-02 → 12 °C).
_DEMO_THRESHOLDS: list[tuple[str | None, str, str, float, str]] = [
    (None, "humidity", ">", 70.0, "warning"),
    ("room-02", "air_temp", ">", 8.0, "critical"),
]


def apply_demo_thresholds() -> int:
    """Записать демо-пороги, если таблица порогов пуста; вернуть число вставленных.

    Идемпотентность намеренно простая: если пороги уже есть (заведены ранее или
    оператором), демо их не трогает и ничего не добавляет.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(_database_url())
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM thresholds")).scalar() or 0
        if existing:
            return 0
        inserted = 0
        for room, metric, op, value, severity in _DEMO_THRESHOLDS:
            conn.execute(
                text(
                    "INSERT INTO thresholds (room_id, metric, op, value, severity, enabled) "
                    "VALUES (:room, :metric, :op, :value, :severity, true)"
                ),
                {"room": room, "metric": metric, "op": op, "value": value, "severity": severity},
            )
            inserted += 1
    return inserted


def main() -> None:
    """CLI-точка: разобрать демо-конфиг и (опционально) записать в БД."""
    parser = argparse.ArgumentParser(description="Демо-сид справочников и порогов")
    parser.add_argument("--apply", action="store_true", help="записать в БД (иначе проверка)")
    args = parser.parse_args()

    rooms, nodes, cameras = load_config(DEMO_CONFIG)
    print(f"Демо-конфиг: помещений={len(rooms)}, узлов={len(nodes)}, камер={len(cameras)}")
    if not args.apply:
        print("Режим проверки (dry-run): запись не выполнялась. Для записи добавьте --apply.")
        return

    apply(rooms, nodes, cameras)
    added = apply_demo_thresholds()
    print(f"Справочники записаны; демо-порогов добавлено: {added}")


if __name__ == "__main__":
    main()
