# Multi-stage образ scheduler (E9.1) — воркер-демон планировщика.
# Контекст сборки — КОРЕНЬ репозитория: нужен и локальный пакет shared
# (monitoring-shared), и сам сервис. Запуск:
#   docker build -f services/scheduler/Dockerfile -t scheduler .

# ── Стадия сборки: ставим зависимости в изолированный virtualenv ──
FROM python:3.12-slim AS builder
WORKDIR /build
# Сначала общий пакет shared (его требует scheduler как monitoring-shared),
# затем сам сервис — порядок важен: локальная зависимость ставится первой.
COPY shared/ ./shared/
COPY services/scheduler/ ./scheduler/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir ./shared ./scheduler

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
# Демон планировщика: периодически создаёт задания по расписаниям.
CMD ["python", "-m", "scheduler.main"]
