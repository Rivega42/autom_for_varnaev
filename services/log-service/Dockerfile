# Multi-stage образ log-service (E9.1).
# Контекст сборки — КОРЕНЬ репозитория: нужен и локальный пакет shared
# (monitoring-shared), и сам сервис. Запуск:
#   docker build -f services/log-service/Dockerfile -t log-service .

# ── Стадия сборки: ставим зависимости в изолированный virtualenv ──
FROM python:3.12-slim AS builder
WORKDIR /build
# Сначала общий пакет shared (его требует log-service как monitoring-shared),
# затем сам сервис — порядок важен: локальная зависимость ставится первой.
COPY shared/ ./shared/
COPY services/log-service/ ./log-service/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir ./shared ./log-service

# ── Стадия запуска: тонкий runtime без инструментов сборки ──
FROM python:3.12-slim AS runtime
# Непривилегированный пользователь (не root).
RUN useradd --create-home --uid 10001 appuser
# Готовое окружение из стадии сборки.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER appuser
EXPOSE 8000
# Запуск ASGI-приложения лог-сервиса (log_service.app:app).
CMD ["uvicorn", "log_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
