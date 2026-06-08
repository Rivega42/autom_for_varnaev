# Образ применения миграций Alembic (one-shot).
# Поднимается сервисом `migrate` в docker-compose ПЕРЕД прикладными сервисами и
# приводит схему БД к последней ревизии (`alembic upgrade head`). Прикладные
# сервисы зависят от его успешного завершения (service_completed_successfully),
# поэтому стартуют уже на готовой схеме.
#
# Контекст сборки — КОРЕНЬ репозитория (нужны alembic.ini и каталог db/migrations).
# Сборка вручную:
#   docker build -f db/Dockerfile -t monitoring-migrate .

FROM python:3.12-slim
WORKDIR /app

# Только то, что нужно для прогона миграций. Миграции пишутся явным SQL
# (target_metadata=None в env.py), модели сервисов и shared/ здесь не требуются.
RUN pip install --no-cache-dir \
    "alembic>=1.13,<2" \
    "sqlalchemy>=2.0,<3" \
    "psycopg2-binary>=2.9"

# Непривилегированный пользователь (не root).
RUN useradd --create-home --uid 10001 appuser

# Конфиг Alembic и сами миграции. URL БД собирается из POSTGRES_* в env.py.
COPY alembic.ini ./alembic.ini
COPY db/migrations ./db/migrations

USER appuser
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Применить все миграции до последней ревизии и завершиться.
CMD ["alembic", "upgrade", "head"]
