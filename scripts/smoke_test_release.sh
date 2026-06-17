#!/usr/bin/env bash
# Smoke-тест финального релизного стека на чистом хосте (фидбэк девопса заказчика).
# Поднимает стек по docker-compose.release.yml, ждёт готовности и проверяет
# ключевые эндпойнты: /api/v1/health, /ui/, /ui/overview.html, Grafana, ps.
#
# Запуск ИЗ каталога бандла (где лежат docker-compose.release.yml и .env), на
# машине, где образы уже загружены (docker load -i images.tar):
#   bash smoke_test_release.sh
#
# Код возврата 0 — все проверки прошли; иначе 1 (для CI).
set -uo pipefail

COMPOSE=(docker compose -f docker-compose.release.yml)
HOST="${SMOKE_HOST:-localhost}"
KEEP="${SMOKE_KEEP:-0}"   # 1 = не гасить стек после теста
fail=0

# API_KEY из .env (нужен для REST-эндпойнтов)
API_KEY="$(grep -E '^API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | awk '{print $1}')"
[ -n "$API_KEY" ] || echo "ВНИМАНИЕ: API_KEY не найден в .env — REST-проверки могут вернуть 401"

echo "== поднимаю релизный стек =="
"${COMPOSE[@]}" up -d || { echo "ОШИБКА: compose up не удался"; exit 1; }

echo "== жду готовности api-gateway (до ~180 c) =="
ready=0
for _ in $(seq 1 60); do
  if curl -fsS -H "X-API-Key: ${API_KEY}" "http://${HOST}:8000/api/v1/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 3
done
[ "$ready" = 1 ] || { echo "✗ api-gateway не ответил за отведённое время"; fail=1; }

check() {  # url описание [доп. curl-аргументы]
  local url="$1" desc="$2"; shift 2
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$@" "$url" 2>/dev/null)"
  if [ "$code" = "200" ]; then echo "  ✓ ${desc} (${code})"; else echo "  ✗ ${desc} (HTTP ${code})"; fail=1; fi
}

echo "== проверки эндпойнтов =="
check "http://${HOST}:8000/api/v1/health"        "REST /api/v1/health"            -H "X-API-Key: ${API_KEY}"
check "http://${HOST}:8000/ui/"                  "GUI /ui/ (static)"              -H "X-API-Key: ${API_KEY}"
check "http://${HOST}:8000/ui/overview.html"     "Экран дежурного /ui/overview"   -H "X-API-Key: ${API_KEY}"
check "http://${HOST}:3000/api/health"           "Grafana /api/health"

echo "== docker compose ps =="
"${COMPOSE[@]}" ps

if [ "$KEEP" != "1" ]; then
  echo "== гашу стек (SMOKE_KEEP=1 чтобы оставить) =="
  "${COMPOSE[@]}" down >/dev/null 2>&1 || true
fi

if [ "$fail" = 0 ]; then echo "SMOKE: ВСЁ ОК ✓"; else echo "SMOKE: ЕСТЬ ПРОВАЛЫ ✗"; fi
exit "$fail"
