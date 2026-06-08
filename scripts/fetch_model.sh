#!/usr/bin/env bash
# Скачать модель MediaPipe PoseLandmarker в models/pose_landmarker.task.
# Вариант модели можно переопределить переменной ANALYTICS_MODEL_URL.
set -euo pipefail
cd "$(dirname "$0")/.."

URL="${ANALYTICS_MODEL_URL:-https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task}"
DEST="models/pose_landmarker.task"

if [ -f "$DEST" ]; then
  echo "Модель уже на месте: $DEST — пропуск."
  exit 0
fi

mkdir -p models
echo "Скачиваю модель PoseLandmarker:"
echo "  $URL"
curl -fSL "$URL" -o "$DEST"
echo "Готово: $DEST ($(du -h "$DEST" | cut -f1))"
