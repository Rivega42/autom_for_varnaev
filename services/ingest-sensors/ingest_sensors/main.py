"""Точка входа воркера ingest-sensors."""

from __future__ import annotations

import logging

from ingest_sensors.mqtt import run


def main() -> None:
    """Настроить логирование и запустить воркер."""
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__":
    main()
