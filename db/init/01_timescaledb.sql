-- Включение расширения TimescaleDB при первой инициализации БД.
-- Скрипты из db/init монтируются в /docker-entrypoint-initdb.d и выполняются
-- образом PostgreSQL ОДИН РАЗ при создании кластера — ДО миграций Alembic.
-- Поэтому к моменту первой миграции (hypertable в E1.5) расширение уже доступно.
CREATE EXTENSION IF NOT EXISTS timescaledb;
