#!/usr/bin/env bash
# Вендоринг веб-ассетов для браузерного живого анализа (static/live.html), чтобы
# клиенты НЕ ходили на CDN: MediaPipe Tasks Vision (JS+WASM), модель
# PoseLandmarker и hls.js кладутся в static/vendor api-gateway.
#
# Каталог static/vendor в .gitignore (бинарники ~25 МБ не коммитим) и попадает в
# образ api-gateway при сборке — поэтому запускай ПЕРЕД `docker compose build`
# (bootstrap.sh делает это сам). Версии фиксированы (не @latest) для воспроизводимости.
set -euo pipefail
cd "$(dirname "$0")/.."

VER="${MEDIAPIPE_TASKS_VERSION:-0.10.18}"
HLS_VER="${HLS_JS_VERSION:-1.5.17}"
MODEL_URL="${LIVE_MODEL_URL:-https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task}"
CDN="https://cdn.jsdelivr.net/npm"
DEST="services/api-gateway/api_gateway/static/vendor"

mkdir -p "$DEST/mediapipe/wasm" "$DEST/model"

get() {  # url dest
  if [ -f "$2" ]; then echo "  есть — $2"; return; fi
  echo "  скачиваю → $2"
  curl -fSL "$1" -o "$2"
}

echo "MediaPipe tasks-vision $VER:"
get "$CDN/@mediapipe/tasks-vision@$VER/vision_bundle.mjs" "$DEST/mediapipe/vision_bundle.mjs"
for f in vision_wasm_internal.js vision_wasm_internal.wasm \
         vision_wasm_nosimd_internal.js vision_wasm_nosimd_internal.wasm; do
  get "$CDN/@mediapipe/tasks-vision@$VER/wasm/$f" "$DEST/mediapipe/wasm/$f"
done

echo "hls.js $HLS_VER:"
get "$CDN/hls.js@$HLS_VER/dist/hls.min.js" "$DEST/hls.min.js"

echo "Модель PoseLandmarker (lite):"
get "$MODEL_URL" "$DEST/model/pose_landmarker.task"

echo "Готово: ассеты в $DEST (live.html грузит их локально, без CDN)."
