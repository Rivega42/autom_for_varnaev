# Node-воркер видеоаналитики (эпик #241 Фаза 3, #255).
# Единое JS-ядро analysis-core + MediaPipe в Node + кадры из RTSP/файла (ffmpeg).
# Контекст сборки — корень репозитория (нужны analysis-core и вендоренные
# ассеты MediaPipe — те же файлы, что использует браузерный «Живой анализ»).
FROM node:22-slim

# ffmpeg — извлечение сырых кадров из RTSP-потока/видеофайла.
# xvfb + Mesa — headless-gl (WebGL для MediaPipe) на Linux требует X-дисплей:
# без него контекст не создаётся (emscripten_webgl_create_context -> error 0),
# поэтому воркер запускается под xvfb-run (виртуальный дисплей в памяти).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        xvfb \
        xauth \
        libgl1 \
        libglx-mesa0 \
        libgl1-mesa-dri \
        libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Единое ядро аналитики (относительный импорт ../analysis-core из воркера).
COPY services/analysis-core/ ./services/analysis-core/
COPY services/video-analytics-node/ ./services/video-analytics-node/

# Ассеты MediaPipe ставятся npm-пакетом @mediapipe/tasks-vision, версия
# зафиксирована в package.json = версии браузерных вендоренных ассетов
# (scripts/fetch_web_assets.sh, MEDIAPIPE_TASKS_VERSION) — движок один.
WORKDIR /app/services/video-analytics-node
RUN npm install --omit=dev --no-audit --no-fund

# Пути к ассетам MediaPipe внутри образа (читает bin/worker.mjs).
ENV MEDIAPIPE_WASM_DIR=/app/services/video-analytics-node/node_modules/@mediapipe/tasks-vision/wasm \
    MEDIAPIPE_BUNDLE=/app/services/video-analytics-node/node_modules/@mediapipe/tasks-vision/vision_bundle.mjs

USER appuser
# Entrypoint поднимает Xvfb (см. комментарий в скрипте: xvfb-run как PID 1
# контейнера зависает) и exec'ает команду; node сам обрабатывает SIGTERM.
ENTRYPOINT ["bash", "docker-entrypoint.sh"]
CMD ["node", "bin/worker.mjs"]
