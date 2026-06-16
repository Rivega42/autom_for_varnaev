#!/usr/bin/env bash
# Снимок БД 1-в-1 с САНИТАЦИЕЙ секретов — для офлайн-бандла «полная копия».
#
# Зачем именно копия ТОМА, а не pg_dump: TimescaleDB (гипертаблицы) логически
# восстанавливается сложно и хрупко; копия каталога данных + crash-recovery даёт
# побайтово те же данные без логического restore. На копии (не на боевой БД!)
# чистим секреты и нормализуем пароли ролей под шаблон .env, иначе сервисы
# заказчика не пройдут аутентификацию к преднаполненной БД.
#
# Запуск на НАШЕЙ машине (боевой стек поднят):
#   ./scripts/snapshot_db.sh
# Результат: delivery/customer-bundle/db_snapshot/db_data.tar.gz + restore-скрипты.
set -euo pipefail

SRC_VOL="${SRC_VOL:-autom_for_varnaev_db_data}"
SRC_DB_CONTAINER="${SRC_DB_CONTAINER:-autom_for_varnaev-db-1}"
OUT="${OUT:-delivery/customer-bundle}"
PGIMAGE="${PGIMAGE:-timescale/timescaledb:2.17.2-pg16}"
# Пароли ролей в снимке нормализуем к этим значениям (совпадают с .env.example,
# который кладётся в бандл как .env). Так стек заказчика стартует «из коробки».
NORM_PG_PASS="${NORM_PG_PASS:-change-me}"
SUFFIX="$$"
WORK_VOL="varnaev_snap_vol_${SUFFIX}"
TMP_PG="varnaev_snap_pg_${SUFFIX}"

cd "$(dirname "$0")/.."
mkdir -p "$OUT/db_snapshot"

PGUSER="$(docker exec "$SRC_DB_CONTAINER" sh -c 'printf %s "$POSTGRES_USER"')"
PGDB="$(docker exec "$SRC_DB_CONTAINER" sh -c 'printf %s "$POSTGRES_DB"')"
PGPASS="$(docker exec "$SRC_DB_CONTAINER" sh -c 'printf %s "$POSTGRES_PASSWORD"')"
PGRO="$(docker exec "$SRC_DB_CONTAINER" sh -c 'printf %s "${POSTGRES_RO_USER:-grafana_ro}"')"
: "${PGUSER:?нет POSTGRES_USER}"; : "${PGDB:?нет POSTGRES_DB}"; : "${PGPASS:?нет POSTGRES_PASSWORD}"

cleanup() {
  docker rm -f "$TMP_PG" >/dev/null 2>&1 || true
  docker volume rm "$WORK_VOL" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== CHECKPOINT на боевой БД (уменьшить WAL-replay в копии) =="
docker exec -e PGPASSWORD="$PGPASS" "$SRC_DB_CONTAINER" \
  psql -h 127.0.0.1 -U "$PGUSER" -d "$PGDB" -c "CHECKPOINT;" >/dev/null

echo "== копирую том $SRC_VOL -> $WORK_VOL =="
docker volume create "$WORK_VOL" >/dev/null
docker run --rm -v "${SRC_VOL}":/from:ro -v "${WORK_VOL}":/to alpine sh -c 'cp -a /from/. /to/'

echo "== поднимаю временный postgres на копии (crash-recovery) =="
docker run -d --name "$TMP_PG" -v "${WORK_VOL}":/var/lib/postgresql/data "$PGIMAGE" >/dev/null
ready=""
for _ in $(seq 1 40); do
  if docker exec "$TMP_PG" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[ -n "$ready" ] || { echo "ОШИБКА: временный postgres не поднялся"; docker logs --tail 30 "$TMP_PG"; exit 1; }

echo "== САНИТАЦИЯ: пароли камер, лицензия, нормализация паролей ролей =="
docker exec -i -e PGPASSWORD="$PGPASS" "$TMP_PG" \
  psql -h 127.0.0.1 -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 <<SQL
-- 1) вырезаем учётные данные из RTSP-URL камер
UPDATE cameras
   SET rtsp_url = regexp_replace(rtsp_url, '://[^/@]+@', '://CUSTOMER:CHANGE_ME@')
 WHERE rtsp_url ~ '://[^/@]+@';
-- 2) убираем лицензионный ключ вендора (заказчик впишет свой)
DELETE FROM app_config WHERE key IN ('license_key');
-- 3) нормализуем пароли ролей под шаблон .env, чтобы стек заказчика стартовал
ALTER ROLE "$PGUSER" WITH PASSWORD '$NORM_PG_PASS';
SQL
# read-only роль (Grafana) — если есть
docker exec -e PGPASSWORD="$PGPASS" "$TMP_PG" \
  psql -h 127.0.0.1 -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 -c \
  "DO \$\$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$PGRO') THEN EXECUTE format('ALTER ROLE %I WITH PASSWORD %L', '$PGRO', '$NORM_PG_PASS'); END IF; END \$\$;"

echo "== контроль: секретов не осталось =="
left="$(docker exec -e PGPASSWORD="$NORM_PG_PASS" "$TMP_PG" psql -h 127.0.0.1 -U "$PGUSER" -d "$PGDB" -At -c \
  "select (select count(*) from cameras where rtsp_url ~ '://[^/@:]+:[^/@]+@' and rtsp_url not like '%CHANGE_ME%')
        + (select count(*) from app_config where key='license_key');")"
[ "${left:-1}" = "0" ] || { echo "ОШИБКА: секреты остались (счёт=$left)"; exit 1; }
echo "   ок: камеры обезличены, лицензия удалена, пароли ролей = '$NORM_PG_PASS'"

echo "== корректно останавливаю временный postgres =="
docker stop "$TMP_PG" >/dev/null

echo "== архивирую санитизированный том =="
docker run --rm -v "${WORK_VOL}":/from:ro alpine sh -c 'cd /from && tar czf - .' > "$OUT/db_snapshot/db_data.tar.gz"

# restore-скрипты для заказчика
cat > "$OUT/db_snapshot/restore_db.sh" <<'DOC'
#!/usr/bin/env bash
# Восстановить снимок БД вендора (данные 1-в-1). Запускать ДО первого `up`.
set -euo pipefail
cd "$(dirname "$0")/.."
VOL="${1:-varnaev_db_data}"
echo "Создаю том $VOL и распаковываю снимок..."
docker volume create "$VOL" >/dev/null
docker run --rm -v "$VOL":/to -v "$PWD/db_snapshot/db_data.tar.gz":/snap.tgz:ro alpine sh -c 'cd /to && tar xzf /snap.tgz'
echo "Готово. Запуск: docker compose -f docker-compose.release.yml up -d"
DOC
cat > "$OUT/db_snapshot/restore_db.ps1" <<'DOC'
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Vol = if ($args[0]) { $args[0] } else { "varnaev_db_data" }
Write-Host "Создаю том $Vol и распаковываю снимок..."
docker volume create $Vol | Out-Null
docker run --rm -v "${Vol}:/to" -v "$PWD/db_snapshot/db_data.tar.gz:/snap.tgz:ro" alpine sh -c 'cd /to && tar xzf /snap.tgz'
Write-Host "Готово. Запуск: docker compose -f docker-compose.release.yml up -d"
DOC

cat > "$OUT/db_snapshot/README.md" <<'DOC'
# Снимок БД вендора (данные 1-в-1)

`db_data.tar.gz` — побайтовая копия каталога данных PostgreSQL/TimescaleDB вендора
с теми же справочниками, показаниями и событиями (дашборды будут заполнены сразу).
Секреты вырезаны: учётные данные RTSP-камер обезличены, лицензионный ключ удалён.

## Как восстановить (ДО первого запуска стека)

1. Загрузи образы: `docker load -i ../images.tar` (или `../install.ps1`).
2. Восстанови БД в том:
   - Windows:   `./restore_db.ps1`
   - Linux/Mac: `bash restore_db.sh`
3. Подними стек: `docker compose -f docker-compose.release.yml up -d`.
4. Открой `http://localhost:8000/ui/overview.html` и Grafana `:3000` — увидишь
   данные вендора.

## Важно про пароли

Пароли ролей БД в снимке выставлены в `change-me` (совпадает с `.env`), чтобы стек
поднялся сразу. Для боевого использования смени пароли БД так:
`ALTER ROLE <роль> WITH PASSWORD '<новый>';` И синхронно в `.env`
(`POSTGRES_PASSWORD`, `POSTGRES_RO_PASSWORD`). Либо начни с чистой БД: удали том
(`docker volume rm varnaev_db_data`) и подними без восстановления снимка.

Лицензию заказчик вписывает свою (`LICENSE_KEY` в `.env`); без неё — демо-режим.
Камеры (`media-gateway/go2rtc.yaml`) заполняются своими адресами.
DOC

chmod +x "$OUT/db_snapshot/restore_db.sh" 2>/dev/null || true
ls -lh "$OUT/db_snapshot/db_data.tar.gz"
echo "Снимок БД готов: $OUT/db_snapshot/"
