#!/usr/bin/env bash
# Сборка ОФЛАЙН-бандла поставки заказчику: образы (docker save) + конфиги + compose.
# Заказчику НЕ нужен ни реестр (ghcr), ни доступ к нашему репозиторию — он получает
# один каталог/архив, делает `docker load` и `docker compose up`.
#
# Запуск НА НАШЕЙ машине из корня репозитория:
#   ./scripts/build_offline_bundle.sh            # MODE=fast по умолчанию
#   MODE=closed ./scripts/build_offline_bundle.sh   # закрытые образы (Nuitka) для gateway/analytics
#
# MODE=fast  — берёт УЖЕ собранные локально образы (docker compose build). Быстро,
#              точная копия того, что крутится у нас. В образах есть байткод.
# MODE=closed — пересобирает api-gateway и video-analytics закрытыми (Nuitka/distroless).
#
# Результат: delivery/customer-bundle/ (в .gitignore). Положи его куда удобно
# (диск/USB/облако) и передай заказчику. Инструкция внутри — START_HERE.md.
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/rivega42}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
MODE="${MODE:-fast}"
OUT="${OUT:-delivery/customer-bundle}"
PROJECT="${PROJECT:-autom_for_varnaev}"   # префикс локальных dev-образов (имя compose-проекта)

cd "$(dirname "$0")/.."
echo "== Офлайн-бандл: MODE=${MODE}, тег ${IMAGE_TAG}, выход ${OUT} =="
rm -rf "$OUT"
mkdir -p "$OUT"

# Целевое_имя : Dockerfile : локальный_dev-образ(для MODE=fast)
IMAGES=(
  "varnaev-migrate:db/Dockerfile:${PROJECT}-migrate"
  "varnaev-log-service:services/log-service/Dockerfile:${PROJECT}-log-service"
  "varnaev-ingest-sensors:services/ingest-sensors/Dockerfile:${PROJECT}-ingest-sensors"
  "varnaev-scheduler:services/scheduler/Dockerfile:${PROJECT}-scheduler"
  "varnaev-backup:db/Dockerfile.backup:${PROJECT}-backup"
  "varnaev-seed:db/Dockerfile.seed:${PROJECT}-demo-seed"
  "varnaev-demo-sensors:services/demo-sensors/Dockerfile:${PROJECT}-demo-sensors"
  "varnaev-api-gateway:services/api-gateway/Dockerfile.release:${PROJECT}-api-gateway"
  "varnaev-video-analytics:services/video-analytics/Dockerfile.release:${PROJECT}-video-analytics"
)
THIRD_PARTY=(
  "timescale/timescaledb:2.17.2-pg16"
  "eclipse-mosquitto:2"
  "alexxit/go2rtc:latest"
  "grafana/grafana:11.3.0"
)

OUR_REFS=()
for item in "${IMAGES[@]}"; do
  IFS=':' read -r name dockerfile devimg <<< "$item"
  ref="${REGISTRY}/${name}:${IMAGE_TAG}"
  if [[ "$MODE" == "closed" ]]; then
    echo "-- сборка $ref (-f $dockerfile)"
    docker build -f "$dockerfile" -t "$ref" .
  else
    src="${devimg}:latest"
    if ! docker image inspect "$src" >/dev/null 2>&1; then
      echo "ОШИБКА: нет локального образа $src. Сначала собери стек:"
      echo "  docker compose build  &&  docker compose -f docker-compose.yml -f docker-compose.demo.yml build"
      exit 1
    fi
    echo "-- тег $src -> $ref"
    docker tag "$src" "$ref"
  fi
  OUR_REFS+=("$ref")
done

echo "== сторонние образы (pull; при сбое сети — локальная копия) =="
for img in "${THIRD_PARTY[@]}"; do
  if docker pull "$img" 2>/dev/null; then
    :
  elif docker image inspect "$img" >/dev/null 2>&1; then
    echo "   pull не удался — беру локальную копию: $img"
  else
    echo "ОШИБКА: образа $img нет ни в сети, ни локально"; exit 1
  fi
done

echo "== docker save -> $OUT/images.tar (это долго и весит несколько ГБ) =="
docker save -o "$OUT/images.tar" "${OUR_REFS[@]}" "${THIRD_PARTY[@]}"

echo "== копирую compose, конфиги и доки (БЕЗ секретов) =="
cp docker-compose.release.yml docker-compose.demo.release.yml "$OUT/"
# .env — ШАБЛОН без секретов (заказчик впишет свои пароли/лицензию)
cp .env.example "$OUT/.env"
# конфиги объекта (не содержат секретов — пароли приходят через env в рантайме)
mkdir -p "$OUT/db" "$OUT/mqtt" "$OUT/grafana" "$OUT/config" "$OUT/media-gateway" "$OUT/models" "$OUT/firmware/esphome" "$OUT/docs"
cp -r db/init "$OUT/db/"
mkdir -p "$OUT/db/seeds"
cp db/seeds/demo.yaml db/seeds/object.example.yaml "$OUT/db/seeds/"
cp mqtt/mosquitto.conf "$OUT/mqtt/"
cp -r grafana/provisioning grafana/dashboards "$OUT/grafana/"
cp config/schedules.example.json "$OUT/config/"
[ -f config/README.md ] && cp config/README.md "$OUT/config/"
# ТОЛЬКО пример go2rtc (НЕ go2rtc.yaml — там пароли камер!)
cp media-gateway/go2rtc.yaml.example "$OUT/media-gateway/"
[ -f media-gateway/README.md ] && cp media-gateway/README.md "$OUT/media-gateway/"
# модель видеоаналитики (если есть)
[ -f models/pose_landmarker.task ] && cp models/pose_landmarker.task "$OUT/models/"
[ -f models/README.md ] && cp models/README.md "$OUT/models/"
# ESPHome — ТОЛЬКО примеры (НЕ secrets.yaml и НЕ node-0X.yaml — там WiFi-пароли!)
cp firmware/esphome/*.example.yaml "$OUT/firmware/esphome/" 2>/dev/null || true
[ -f firmware/esphome/secrets.yaml.example ] && cp firmware/esphome/secrets.yaml.example "$OUT/firmware/esphome/"
[ -f firmware/esphome/README.md ] && cp firmware/esphome/README.md "$OUT/firmware/esphome/"
[ -f firmware/esphome/.gitignore ] && cp firmware/esphome/.gitignore "$OUT/firmware/esphome/"
# доки
cp docs/DEPLOY_CUSTOMER.md "$OUT/docs/"

echo "== генерирую START_HERE.md и install-скрипты в бандле =="
cat > "$OUT/START_HERE.md" <<'DOC'
# Развёртывание — начни отсюда (офлайн-поставка)

Это **полная самодостаточная копия** системы мониторинга. Реестр и интернет для
образов **не нужны** — все образы лежат в `images.tar`. Нужен только установленный
**Docker** (Docker Desktop на Windows / Docker Engine на Linux).

## Шаги

1. **Загрузить образы** в Docker (один раз, несколько ГБ):
   - Linux/Mac:   `bash install.sh`
   - Windows:     `./install.ps1`
   (то же вручную: `docker load -i images.tar`)

2. **Заполнить `.env`** (открой файл, задай пароли и лицензию):
   - `POSTGRES_PASSWORD`, `POSTGRES_RO_PASSWORD` — придумай длинные пароли;
   - `API_KEY` — длинная случайная строка (ключ доступа к интерфейсу);
   - `GF_SECURITY_ADMIN_PASSWORD` — пароль входа в Grafana;
   - `LICENSE_KEY` — лицензионный ключ (если прислан; без него демо-режим 1/1/1).

3. **(Опц.) камеры** — скопируй пример и впиши свои RTSP-адреса:
   - `media-gateway/go2rtc.yaml.example` → `media-gateway/go2rtc.yaml`.

4. **Запуск:**
   - «Боевой» (пустые справочники, заполняешь свой объект):
     `docker compose -f docker-compose.release.yml up -d`
   - **«Демо, как у вендора»** (сразу видно populated-дашборды на синтетике):
     `docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d`

5. **Открыть в браузере** (с этого же ПК или по IP сервера):
   - Интерфейс: `http://ЛОКАЛХОСТ:8000/ui/` (введи `API_KEY` в шапке)
   - Экран дежурного: `http://ЛОКАЛХОСТ:8000/ui/overview.html`
   - Grafana: `http://ЛОКАЛХОСТ:3000` (admin / пароль из `.env`)

Подробная инструкция (проверка, эксплуатация, обновление, траблшутинг) —
`docs/DEPLOY_CUSTOMER.md`. Управление сервисами — `docker compose -f docker-compose.release.yml ps|logs|down`.
DOC

cat > "$OUT/install.sh" <<'DOC'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Загружаю образы из images.tar в Docker (это займёт время)..."
docker load -i images.tar
[ -f .env ] || cp .env.example .env 2>/dev/null || true
echo "Готово. Дальше: заполни .env и запусти:"
echo "  docker compose -f docker-compose.release.yml up -d"
echo "Демо как у вендора:"
echo "  docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d"
DOC

cat > "$OUT/install.ps1" <<'DOC'
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Загружаю образы из images.tar в Docker (это займёт время)..."
docker load -i images.tar
Write-Host "Готово. Дальше: заполни .env и запусти:"
Write-Host "  docker compose -f docker-compose.release.yml up -d"
Write-Host "Демо как у вендора:"
Write-Host "  docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d"
DOC
chmod +x "$OUT/install.sh" 2>/dev/null || true

# Размер бандла
size=$(du -sh "$OUT" 2>/dev/null | cut -f1 || echo "?")
echo "== ГОТОВО. Бандл: $OUT (размер ~${size}) =="
echo "   Положи каталог (или его архив) куда удобно и передай заказчику."
echo "   Заархивировать: tar -czf customer-bundle-${IMAGE_TAG}.tar.gz -C \"$(dirname "$OUT")\" \"$(basename "$OUT")\""
