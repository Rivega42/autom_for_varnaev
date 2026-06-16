# Сборка и публикация закрытых образов наших сервисов в реестр (Plan B), Windows.
# Запускать НА НАШЕЙ машине (не у заказчика). Подробно — docs/DEPLOY_CUSTOMER.md.
#
# Использование (PowerShell, из корня репозитория):
#   $env:REGISTRY="ghcr.io/rivega42"; $env:IMAGE_TAG="v1.0.0"; $env:GHCR_TOKEN="<PAT>"
#   ./scripts/publish_release_images.ps1
#
# Требуется Docker и доступ к реестру: либо заранее `docker login ghcr.io`, либо
# переменная окружения GHCR_TOKEN с PAT (scope write:packages) — логин сделает скрипт.
$ErrorActionPreference = "Stop"

$registry = if ($env:REGISTRY) { $env:REGISTRY } else { "ghcr.io/rivega42" }
$tag      = if ($env:IMAGE_TAG) { $env:IMAGE_TAG } else { "v1.0.0" }
$ghcrUser = if ($env:GHCR_USER) { $env:GHCR_USER } else { "Rivega42" }

# Корень репозитория (контекст сборки), относительно расположения скрипта.
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Имя образа → Dockerfile. api-gateway и video-analytics — ЗАКРЫТЫЕ (Dockerfile.release).
$images = [ordered]@{
  "varnaev-migrate"         = "db/Dockerfile"
  "varnaev-log-service"     = "services/log-service/Dockerfile"
  "varnaev-ingest-sensors"  = "services/ingest-sensors/Dockerfile"
  "varnaev-scheduler"       = "services/scheduler/Dockerfile"
  "varnaev-backup"          = "db/Dockerfile.backup"
  "varnaev-seed"            = "db/Dockerfile.seed"
  "varnaev-api-gateway"     = "services/api-gateway/Dockerfile.release"
  "varnaev-video-analytics" = "services/video-analytics/Dockerfile.release"
}

Write-Host "==> Реестр: $registry   тег: $tag"

# Логин (если передан токен).
if ($env:GHCR_TOKEN) {
  $registryHost = $registry.Split("/")[0]   # ghcr.io
  Write-Host "==> Логин в $registryHost как $ghcrUser"
  $env:GHCR_TOKEN | docker login $registryHost -u $ghcrUser --password-stdin
  if ($LASTEXITCODE -ne 0) { throw "docker login завершился с ошибкой" }
}

# 1) Сборка.
foreach ($name in $images.Keys) {
  $dockerfile = $images[$name]
  Write-Host "==> Сборка $registry/${name}:$tag  (-f $dockerfile)"
  docker build -f $dockerfile -t "$registry/${name}:$tag" .
  if ($LASTEXITCODE -ne 0) { throw "Сборка $name завершилась с ошибкой" }
}

# 2) Публикация.
foreach ($name in $images.Keys) {
  Write-Host "==> Публикация $registry/${name}:$tag"
  docker push "$registry/${name}:$tag"
  if ($LASTEXITCODE -ne 0) { throw "Публикация $name завершилась с ошибкой" }
}

Write-Host "==> Готово. Опубликовано образов: $($images.Count) (тег $tag)."
Write-Host "    Не забудь сделать пакеты ghcr публичными (или выдать заказчику read:packages)."
