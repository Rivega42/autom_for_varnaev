# db

Схема БД (TimescaleDB = PostgreSQL 16 + расширение `timescaledb`). `migrations/` — Alembic, `init/` — включение расширения и hypertable. Эпики E0/E1. Модель — `docs/04_DATA_MODEL.md`.

## Порядок инициализации

1. `init/` — SQL-скрипты образа PostgreSQL (`/docker-entrypoint-initdb.d`),
   выполняются один раз при создании кластера. Здесь включается расширение
   `timescaledb` (`init/01_timescaledb.sql`).
2. `migrations/` — Alembic-миграции схемы, применяются после старта БД
   (`alembic upgrade head`).
