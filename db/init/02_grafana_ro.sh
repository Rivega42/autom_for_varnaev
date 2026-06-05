#!/bin/bash
# Создание read-only пользователя для Grafana (grafana_ro).
# Скрипты db/init выполняются образом PostgreSQL ОДИН РАЗ при создании кластера
# (до миграций Alembic). Чтобы права распространялись и на таблицы, которые
# создаст Alembic ПОЗЖЕ под пользователем POSTGRES_USER, выдаём как текущие
# SELECT-права, так и DEFAULT PRIVILEGES на будущие таблицы.
#
# Креды берутся из окружения контейнера db (POSTGRES_RO_USER/POSTGRES_RO_PASSWORD).
# Если ro-пользователь не задан — скрипт ничего не делает.
set -euo pipefail

if [ -z "${POSTGRES_RO_USER:-}" ] || [ -z "${POSTGRES_RO_PASSWORD:-}" ]; then
  echo "grafana_ro: POSTGRES_RO_USER/PASSWORD не заданы — пропускаем создание ro-пользователя"
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_RO_USER}') THEN
      CREATE ROLE "${POSTGRES_RO_USER}" LOGIN PASSWORD '${POSTGRES_RO_PASSWORD}';
    END IF;
  END
  \$\$;

  GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO "${POSTGRES_RO_USER}";
  GRANT USAGE ON SCHEMA public TO "${POSTGRES_RO_USER}";
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO "${POSTGRES_RO_USER}";
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "${POSTGRES_RO_USER}";
EOSQL

echo "grafana_ro: пользователь ${POSTGRES_RO_USER} создан/обновлён (read-only)"
