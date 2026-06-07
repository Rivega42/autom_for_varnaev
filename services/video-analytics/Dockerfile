# Multi-stage образ video-analytics (E9.1) — воркер аналитики (MediaPipe/OpenCV).
# Контекст сборки — КОРЕНЬ репозитория: нужен и локальный пакет shared
# (monitoring-shared), и сам сервис. Запуск:
#   docker build -f services/video-analytics/Dockerfile -t video-analytics .

# ── Стадия сборки: ставим зависимости в изолированный virtualenv ──
FROM python:3.12-slim AS builder
WORKDIR /build
# Сначала общий пакет shared (его требует video-analytics как monitoring-shared),
# затем сам сервис — порядок важен: локальная зависимость ставится первой.
COPY shared/ ./shared/
COPY services/video-analytics/ ./video-analytics/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir ./shared ./video-analytics

# ── Стадия запуска: тонкий runtime + системные либы для OpenCV/MediaPipe ──
FROM python:3.12-slim AS runtime
# libGL и libglib нужны OpenCV/MediaPipe в runtime (даже headless-сборке cv2).
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# Непривилегированный пользователь (не root).
RUN useradd --create-home --uid 10001 appuser
# Готовое окружение из стадии сборки.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER appuser
# Воркер видеоаналитики: берёт задания из очереди и шлёт события в log-service.
CMD ["python", "-m", "video_analytics.main"]
