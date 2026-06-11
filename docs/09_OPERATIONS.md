# 09 · Эксплуатация (runbook)

Практическая заметка для дежурного/DevOps: как поднимать и перезапускать контур,
делать бэкап и восстановление БД, где лежат артефакты и логи. Архитектура —
`01_ARCHITECTURE.md`, сеть и порты — `02_NETWORK.md`.

---

## 1. Что опубликовано наружу

В хост (LAN объекта) проброшены только:

| Порт | Сервис | Назначение |
|---|---|---|
| `8000` | `api-gateway` | единственный внешний REST-вход контура |
| `3000` | `grafana` | дашборды оператора |
| `1883` | `mqtt-broker` | приём показаний от узлов датчиков (ESPHome) |

Остальные сервисы (`db`, `log-service`, `ingest-sensors`, `scheduler`,
`video-analytics`, `media-gateway`, `migrate`) живут только во внутренней сети
`internal` и наружу не видны (см. `02_NETWORK.md`).

---

## 2. Запуск, остановка, перезапуск

Все команды — из корня репозитория (рядом с `docker-compose.yml`), при наличии
заполненного `.env` (`cp .env.example .env`).

```bash
# Поднять весь контур (порядок выдержит compose сам):
#   db (healthy) → migrate (alembic upgrade head) → прикладные сервисы
docker compose up -d

# Состояние и healthcheck'и
docker compose ps

# Перезапуск одного сервиса (например, после смены конфига)
docker compose restart video-analytics

# Остановить контур (тома сохраняются — данные не теряются)
docker compose down

# ВНИМАНИЕ: -v удаляет тома вместе с данными БД и артефактами. Не для прод!
# docker compose down -v
```

Порядок зависимостей задан в compose через `depends_on` + `condition`, поэтому
ручной последовательности обычно не требуется.

---

## 3. Миграции схемы БД

Схему создаёт и обновляет одноразовый сервис `migrate` (`db/Dockerfile`,
`alembic upgrade head`). Он стартует после готовности `db` и завершается до
старта прикладных сервисов — те зависят от его успешного завершения.

```bash
# Применить миграции вручную (например, после добавления новой ревизии)
docker compose run --rm migrate

# Посмотреть текущую ревизию / историю (изнутри образа миграций)
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
```

При **изменении схемы**: добавить ревизию в `db/migrations/versions/`, затем
пересобрать и прогнать `migrate` (`docker compose build migrate && docker compose
run --rm migrate`). Откат — `alembic downgrade <revision>` (осторожно на проде).

---

## 4. Бэкап и восстановление TimescaleDB

Данные БД лежат в томе `db_data`. Делаем логический бэкап через `pg_dump`
(переменные берём из `.env`).

```bash
# Бэкап всей БД в сжатый дамп (формат custom — удобно для pg_restore)
docker compose exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > backup_$(date +%F).dump

# Восстановление в чистую БД (схема будет в дампе; миграции прогонять не нужно)
docker compose exec -T db \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  < backup_2026-01-01.dump
```

### Автоматический бэкап по расписанию (сервис `backup`)

На объекте нет администратора БД, поэтому бэкап делает отдельный сервис
`backup` (см. `docker-compose.yml`, образ `db/Dockerfile.backup`). Он
поднимается в составе дефолтного стека, работает в сети `internal` (БД наружу
не публикуется) и в цикле: `pg_dump` → сжатие в gzip → ротация старых дампов →
сон. Дампы складываются в том `backups` под именами
`monitoring-<db>-<YYYYmmdd-HHMMSS>.sql.gz` (имя сортируется по времени).

Параметры — в `.env`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BACKUP_KEEP` | `14` | сколько последних дампов хранить (`<=0` — ротация выключена) |
| `BACKUP_INTERVAL_H` | `24` | период между бэкапами, часов (минимум 1) |

```bash
# Посмотреть накопленные дампы
docker compose run --rm --entrypoint sh backup -c 'ls -lh /backups'

# Сделать дамп немедленно, один раз (не входя в цикл)
docker compose run --rm -e BACKUP_ONCE=1 backup

# Восстановление: распаковать дамп и подать его в psql внутри контейнера БД.
# (формат — обычный SQL, в отличие от ручного -Fc выше: schema + данные)
docker compose exec -T db sh -c \
  'gunzip -c < /tmp/dump.sql.gz | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Дампы лежат в томе `backups` (см. §7). Рекомендации: периодически копировать
дампы **вне сервера** (том на самом сервере не спасёт от его отказа) и проверять
восстановление на тестовом контуре. Регламент срока хранения временных рядов —
открытый вопрос (issue по `04_DATA_MODEL.md`).

### Свёртки, сжатие и retention сырья (TimescaleDB, #295)

Миграция 0018 включает (применяет сервис `migrate` на TimescaleDB):
- **continuous aggregate** `sensor_readings_hourly` — почасовая свёртка
  (avg/min/max), обновляется раз в час; для быстрых дашбордов на длинных рядах.
- **сжатие** сырья `sensor_readings` (lossless) старше
  `READINGS_COMPRESS_AFTER_DAYS` дней (по умолчанию 7).
- **retention** сырья — `READINGS_RETENTION_DAYS` дней; **0 = выключено**
  (значения финализируются по регламенту заказчика, #41). Включать осознанно:
  retention безвозвратно удаляет старое сырьё (свёртка при этом сохраняется).

```bash
# Что насчитала свёртка / статус политик
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT view_name, materialization_hypertable_name FROM timescaledb_information.continuous_aggregates;"
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT * FROM timescaledb_information.jobs;"   # политики обновления/сжатия/retention
```

---

## 5. Артефакты (скриншоты-доказательства)

`video-analytics` пишет кадры-доказательства на общий том `artifacts`
(в контейнере — `ARTIFACTS_DIR`, по умолчанию `/data/artifacts`). Схема пути
(см. `01_ARCHITECTURE.md` §6):

```
/data/artifacts/<YYYY-MM-DD>/<event_id|task_id>.<ext>
```

```bash
# Посмотреть, что накопилось
docker compose exec video-analytics ls -R /data/artifacts | head

# Удалить артефакты старше 30 дней (чистка диска)
docker compose exec video-analytics \
  find /data/artifacts -type f -mtime +30 -delete
```

В журнал/задание пишется **ссылка** (путь), сам бинарь — только на томе.

---

## 6. Логи и диагностика

```bash
# Логи сервиса (сообщения оператору — на русском, CLAUDE.md §2)
docker compose logs -f --tail=200 ingest-sensors

# Все сервисы сразу
docker compose logs -f

# Состояние healthcheck'ов (healthy/unhealthy)
docker compose ps
```

Healthcheck'и заданы для `db`, `log-service`, `api-gateway`. Если сервис
`unhealthy` — смотреть его логи и доступность зависимостей (БД, log-service).

---

## 7. Тома и их назначение

| Том | Что хранит | Терять нельзя |
|---|---|---|
| `db_data` | БД TimescaleDB (ряды, события, задания) | да |
| `backups` | сжатые дампы БД (сервис `backup`, §4) | желательно (копировать вне сервера) |
| `artifacts` | скриншоты-доказательства видеоаналитики | желательно |
| `mqtt_data` | состояние/сообщения брокера Mosquitto | нет (кэш) |
| `grafana_data` | настройки и состояние Grafana | нет (provisioning как код) |

---

## 8. Пределы защиты кода

Полностью закрыть код от владельца хоста нельзя; меры и их границы (компиляция
Nuitka, distroless, юридический контур) описаны в
`05_SECURITY_CODE_PROTECTION.md`. Release-сборки поднимаются профилем
`docker compose --profile release …` (по умолчанию работают dev-образы).
