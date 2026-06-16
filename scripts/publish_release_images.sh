#!/usr/bin/env bash
# Сборка и публикация закрытых образов наших сервисов в реестр (Plan B).
# Запускать НА НАШЕЙ машине (не у заказчика). Заказчик потом только тянет образы
# по docker-compose.release.yml. Подробно — docs/DEPLOY_CUSTOMER.md §«Публикация».
#
# Использование:
#   REGISTRY=ghcr.io/rivega42 IMAGE_TAG=v1.0.0 GHCR_TOKEN=<PAT> ./scripts/publish_release_images.sh
#
# Требуется:
#   • Docker;
#   • Доступ к реестру: либо заранее `docker login ghcr.io`, либо переменная
#     GHCR_TOKEN с Personal Access Token, имеющим scope write:packages
#     (тогда логин сделает сам скрипт).
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/rivega42}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
GHCR_USER="${GHCR_USER:-Rivega42}"

# Перейти в корень репозитория (контекст сборки — корень, как в compose).
cd "$(dirname "$0")/.."

# Имя_образа → Dockerfile. api-gateway и video-analytics — ЗАКРЫТЫЕ (Dockerfile.release).
IMAGES=(
  "varnaev-migrate:db/Dockerfile"
  "varnaev-log-service:services/log-service/Dockerfile"
  "varnaev-ingest-sensors:services/ingest-sensors/Dockerfile"
  "varnaev-scheduler:services/scheduler/Dockerfile"
  "varnaev-backup:db/Dockerfile.backup"
  "varnaev-seed:db/Dockerfile.seed"
  "varnaev-api-gateway:services/api-gateway/Dockerfile.release"
  "varnaev-video-analytics:services/video-analytics/Dockerfile.release"
)

echo "==> Реестр: ${REGISTRY}   тег: ${IMAGE_TAG}"

# Логин в реестр (если передан токен; иначе считаем, что уже залогинены).
if [[ -n "${GHCR_TOKEN:-}" ]]; then
  registry_host="${REGISTRY%%/*}"   # ghcr.io из ghcr.io/rivega42
  echo "==> Логин в ${registry_host} как ${GHCR_USER}"
  echo "${GHCR_TOKEN}" | docker login "${registry_host}" -u "${GHCR_USER}" --password-stdin
fi

# 1) Сборка всех образов.
for item in "${IMAGES[@]}"; do
  name="${item%%:*}"
  dockerfile="${item#*:}"
  echo "==> Сборка ${REGISTRY}/${name}:${IMAGE_TAG}  (-f ${dockerfile})"
  docker build -f "${dockerfile}" -t "${REGISTRY}/${name}:${IMAGE_TAG}" .
done

# 2) Публикация всех образов.
for item in "${IMAGES[@]}"; do
  name="${item%%:*}"
  echo "==> Публикация ${REGISTRY}/${name}:${IMAGE_TAG}"
  docker push "${REGISTRY}/${name}:${IMAGE_TAG}"
done

echo "==> Готово. Опубликовано образов: ${#IMAGES[@]} (тег ${IMAGE_TAG})."
echo "    Не забудь сделать пакеты ghcr публичными (или выдать заказчику read:packages)."
