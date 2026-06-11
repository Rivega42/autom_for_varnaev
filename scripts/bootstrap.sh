#!/usr/bin/env bash
# Bootstrap контура одной командой. Идемпотентно: повторный запуск не ломает
# уже настроенное.
#
#   scripts/bootstrap.sh           # боевой: .env + модель + справочники + стек
#   scripts/bootstrap.sh --demo    # демо: .env + стек с синтетическими датчиками
#
# Требуется работающий Docker daemon и docker compose v2.
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO=0
[ "${1:-}" = "--demo" ] && DEMO=1

echo "[1] .env (секреты)"
if [ -f .env ]; then
  echo "    .env уже есть — пропуск"
else
  python scripts/init_env.py
fi

echo "[2] Конфиг камер медиа-шлюза (go2rtc)"
if [ -f media-gateway/go2rtc.yaml ]; then
  echo "    media-gateway/go2rtc.yaml уже есть — пропуск"
else
  # Реальный конфиг не в репозитории (пароли камер); создаём из примера,
  # иначе bind-mount compose на несуществующий файл создаст каталог.
  cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml
  echo "    создан из go2rtc.yaml.example — впишите реальные адреса камер"
fi

echo "[3] Веб-ассеты для живого анализа (MediaPipe/модель/hls — локально, без CDN)"
bash scripts/fetch_web_assets.sh \
  || echo "    ВНИМАНИЕ: веб-ассеты не скачаны (нет сети?). Браузерный «Живой анализ» без них не загрузится."

if [ "$DEMO" = "1" ]; then
  echo "[4] Демо-режим: сборка и запуск контура с синтетическими датчиками"
  docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
  echo
  echo "Готово (демо). Данные пойдут сами через ~10–60 с (показания, затем события)."
  echo "  GUI настройки : http://localhost:8000/ui/"
  echo "  Grafana       : http://localhost:3000"
  echo "  API           : http://localhost:8000/api/v1/health"
  exit 0
fi

echo "[4] Модель видеоаналитики"
if [ -f models/pose_landmarker.task ]; then
  echo "    models/pose_landmarker.task уже есть — пропуск"
else
  bash scripts/fetch_model.sh \
    || echo "    ВНИМАНИЕ: модель не скачана (нет сети?). video-analytics без неё не стартует."
fi

echo "[5] Справочники объекта (помещения/узлы/камеры)"
if [ -f db/seeds/object.yaml ]; then
  # Сид зависит от db+migrate — поднимет их и применит справочники ДО старта
  # ingest-sensors (тот читает узлы один раз на старте).
  docker compose --profile seed run --rm seed --apply
else
  echo "    db/seeds/object.yaml не найден — справочники заведите через GUI (/ui/)"
  echo "    или скопируйте db/seeds/object.example.yaml в object.yaml и повторите."
fi

echo "[6] Сборка и запуск стека"
docker compose up -d --build
echo
echo "Готово."
echo "  GUI настройки : http://localhost:8000/ui/"
echo "  Grafana       : http://localhost:3000"
echo "  API           : http://localhost:8000/api/v1/health"
