#!/usr/bin/env bash
# Локальный прогон всех проверок монорепо (как в CI): линт, формат, типы, тесты.
# Использование: scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ruff: линт =="
ruff check .
echo "== ruff: формат =="
ruff format --check .
echo "== mypy: типы =="
mypy .
echo "== pytest: тесты =="
pytest
echo "== всё чисто =="
