# Сборка ОФЛАЙН-бандла поставки заказчику (Windows): образы (docker save) +
# конфиги + compose. Заказчику НЕ нужен реестр и доступ к нашему репозиторию —
# он получает один каталог/архив, делает `docker load` и `docker compose up`.
#
# Запуск НА НАШЕЙ машине из корня репозитория (PowerShell):
#   ./scripts/build_offline_bundle.ps1                       # MODE=fast по умолчанию
#   $env:MODE="closed"; ./scripts/build_offline_bundle.ps1   # закрытые образы (Nuitka)
#
# MODE=fast  — берёт УЖЕ собранные локально образы (точная копия нашего стека).
# MODE=closed — пересобирает api-gateway и video-analytics закрытыми (Nuitka).
# Результат: delivery/customer-bundle/ (в .gitignore). Инструкция внутри — START_HERE.md.
$ErrorActionPreference = "Stop"

$registry = if ($env:REGISTRY) { $env:REGISTRY } else { "ghcr.io/rivega42" }
$tag      = if ($env:IMAGE_TAG) { $env:IMAGE_TAG } else { "v1.0.0" }
$mode     = if ($env:MODE) { $env:MODE } else { "fast" }
$project  = if ($env:PROJECT) { $env:PROJECT } else { "autom_for_varnaev" }
$out      = if ($env:OUT) { $env:OUT } else { "delivery/customer-bundle" }

Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "== Офлайн-бандл: MODE=$mode, тег $tag, выход $out =="
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $out | Out-Null

# Целевое_имя → @{ Dockerfile; Dev (локальный dev-образ для MODE=fast) }
$images = [ordered]@{
  "varnaev-migrate"         = @{ Dockerfile = "db/Dockerfile";                              Dev = "$project-migrate" }
  "varnaev-log-service"     = @{ Dockerfile = "services/log-service/Dockerfile";            Dev = "$project-log-service" }
  "varnaev-ingest-sensors"  = @{ Dockerfile = "services/ingest-sensors/Dockerfile";         Dev = "$project-ingest-sensors" }
  "varnaev-scheduler"       = @{ Dockerfile = "services/scheduler/Dockerfile";              Dev = "$project-scheduler" }
  "varnaev-backup"          = @{ Dockerfile = "db/Dockerfile.backup";                       Dev = "$project-backup" }
  "varnaev-seed"            = @{ Dockerfile = "db/Dockerfile.seed";                         Dev = "$project-demo-seed" }
  "varnaev-demo-sensors"    = @{ Dockerfile = "services/demo-sensors/Dockerfile";           Dev = "$project-demo-sensors" }
  "varnaev-api-gateway"     = @{ Dockerfile = "services/api-gateway/Dockerfile.release";    Dev = "$project-api-gateway" }
  "varnaev-video-analytics" = @{ Dockerfile = "services/video-analytics/Dockerfile.release"; Dev = "$project-video-analytics" }
}
$thirdParty = @(
  "timescale/timescaledb:2.17.2-pg16",
  "eclipse-mosquitto:2",
  "alexxit/go2rtc:latest",
  "grafana/grafana:11.3.0"
)

$ourRefs = @()
foreach ($name in $images.Keys) {
  $ref = "$registry/${name}:$tag"
  if ($mode -eq "closed") {
    Write-Host "-- сборка $ref (-f $($images[$name].Dockerfile))"
    docker build -f $images[$name].Dockerfile -t $ref .
    if ($LASTEXITCODE -ne 0) { throw "Сборка $name не удалась" }
  } else {
    $src = "$($images[$name].Dev):latest"
    docker image inspect $src 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Нет локального образа $src. Сначала собери стек: docker compose build; docker compose -f docker-compose.yml -f docker-compose.demo.yml build"
    }
    Write-Host "-- тег $src -> $ref"
    docker tag $src $ref
  }
  $ourRefs += $ref
}

Write-Host "== сторонние образы (pull; при сбое сети — локальная копия) =="
foreach ($img in $thirdParty) {
  docker pull $img 2>$null
  if ($LASTEXITCODE -ne 0) {
    docker image inspect $img 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Образа $img нет ни в сети, ни локально" }
    Write-Host "   pull не удался — беру локальную копию: $img"
  }
}

Write-Host "== docker save -> $out/images.tar (долго, несколько ГБ) =="
$allRefs = $ourRefs + $thirdParty
docker save -o "$out/images.tar" $allRefs
if ($LASTEXITCODE -ne 0) { throw "docker save не удался" }

Write-Host "== копирую compose, конфиги и доки (БЕЗ секретов) =="
Copy-Item docker-compose.release.yml, docker-compose.demo.release.yml $out
Copy-Item .env.example "$out/.env"   # ШАБЛОН без секретов
foreach ($d in @("db","mqtt","grafana","config","media-gateway","models","firmware/esphome","docs","db/seeds")) {
  New-Item -ItemType Directory -Force -Path "$out/$d" | Out-Null
}
Copy-Item db/init "$out/db/init" -Recurse
Copy-Item db/seeds/demo.yaml, db/seeds/object.example.yaml "$out/db/seeds/"
Copy-Item mqtt/mosquitto.conf "$out/mqtt/"
Copy-Item grafana/provisioning "$out/grafana/provisioning" -Recurse
Copy-Item grafana/dashboards "$out/grafana/dashboards" -Recurse
Copy-Item config/schedules.example.json "$out/config/"
if (Test-Path config/README.md) { Copy-Item config/README.md "$out/config/" }
# ТОЛЬКО пример go2rtc (НЕ go2rtc.yaml — там пароли камер!)
Copy-Item media-gateway/go2rtc.yaml.example "$out/media-gateway/"
if (Test-Path media-gateway/README.md) { Copy-Item media-gateway/README.md "$out/media-gateway/" }
if (Test-Path models/pose_landmarker.task) { Copy-Item models/pose_landmarker.task "$out/models/" }
if (Test-Path models/README.md) { Copy-Item models/README.md "$out/models/" }
# ESPHome — ТОЛЬКО примеры (НЕ secrets.yaml и НЕ node-0X.yaml — там WiFi-пароли!)
Get-ChildItem firmware/esphome/*.example.yaml | Copy-Item -Destination "$out/firmware/esphome/"
if (Test-Path firmware/esphome/secrets.yaml.example) { Copy-Item firmware/esphome/secrets.yaml.example "$out/firmware/esphome/" }
if (Test-Path firmware/esphome/README.md) { Copy-Item firmware/esphome/README.md "$out/firmware/esphome/" }
if (Test-Path firmware/esphome/.gitignore) { Copy-Item firmware/esphome/.gitignore "$out/firmware/esphome/" }
Copy-Item docs/DEPLOY_CUSTOMER.md "$out/docs/"

Write-Host "== генерирую START_HERE.md и install-скрипты в бандле =="
$startHere = @'
# Развёртывание — начни отсюда (офлайн-поставка)

Это **полная самодостаточная копия** системы мониторинга. Реестр и интернет для
образов **не нужны** — все образы лежат в `images.tar`. Нужен только установленный
**Docker** (Docker Desktop на Windows / Docker Engine на Linux).

## Шаги

1. **Загрузить образы** в Docker (один раз, несколько ГБ):
   - Windows:   `./install.ps1`
   - Linux/Mac: `bash install.sh`
   (то же вручную: `docker load -i images.tar`)

2. **Заполнить `.env`** (открой файл, задай пароли и лицензию):
   - `POSTGRES_PASSWORD`, `POSTGRES_RO_PASSWORD` — длинные пароли;
   - `API_KEY` — длинная случайная строка (ключ доступа к интерфейсу);
   - `GF_SECURITY_ADMIN_PASSWORD` — пароль входа в Grafana;
   - `LICENSE_KEY` — лицензионный ключ (без него демо-режим 1/1/1).

3. **(Опц.) камеры** — `media-gateway/go2rtc.yaml.example` → `media-gateway/go2rtc.yaml`, впиши RTSP-адреса.

4. **Запуск:**
   - «Боевой» (свой объект): `docker compose -f docker-compose.release.yml up -d`
   - **«Демо как у вендора»** (populated-дашборды на синтетике):
     `docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d`

5. **Открыть в браузере:**
   - Интерфейс: `http://localhost:8000/ui/` (введи `API_KEY`)
   - Экран дежурного: `http://localhost:8000/ui/overview.html`
   - Grafana: `http://localhost:3000` (admin / пароль из `.env`)

Подробно — `docs/DEPLOY_CUSTOMER.md`.
'@
Set-Content -Path "$out/START_HERE.md" -Value $startHere -Encoding utf8

$installPs = @'
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Загружаю образы из images.tar в Docker (это займёт время)..."
docker load -i images.tar
Write-Host "Готово. Заполни .env и запусти:"
Write-Host "  docker compose -f docker-compose.release.yml up -d"
Write-Host "Демо как у вендора:"
Write-Host "  docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d"
'@
Set-Content -Path "$out/install.ps1" -Value $installPs -Encoding utf8

$installSh = @'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Загружаю образы из images.tar в Docker (это займёт время)..."
docker load -i images.tar
[ -f .env ] || cp .env.example .env 2>/dev/null || true
echo "Готово. Заполни .env и запусти: docker compose -f docker-compose.release.yml up -d"
'@
Set-Content -Path "$out/install.sh" -Value $installSh -Encoding utf8

Write-Host "== ГОТОВО. Бандл: $out =="
Write-Host "   Положи каталог (или его архив) куда удобно и передай заказчику."
Write-Host "   Заархивировать: Compress-Archive -Path $out\* -DestinationPath customer-bundle-$tag.zip"
