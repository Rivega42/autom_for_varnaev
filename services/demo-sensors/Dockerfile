# Multi-stage образ demo-sensors — генератор синтетических показаний (демо-режим).
# Контекст сборки — КОРЕНЬ репозитория: нужен и общий пакет shared
# (monitoring-shared), и сам сервис. Запуск:
#   docker build -f services/demo-sensors/Dockerfile -t demo-sensors .

# ── Стадия сборки: ставим зависимости в изолированный virtualenv ──
FROM python:3.12-slim AS builder
WORKDIR /build
COPY shared/ ./shared/
COPY services/demo-sensors/ ./demo-sensors/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir ./shared ./demo-sensors

# ── Стадия запуска: тонкий runtime без инструментов сборки ──
FROM python:3.12-slim AS runtime
# Непривилегированный пользователь (не root).
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER appuser
# Публикатор без сетевого входа: подключается к MQTT-брокеру и шлёт показания.
CMD ["python", "-m", "demo_sensors.main"]
