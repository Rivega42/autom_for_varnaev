#!/usr/bin/env bash
# Подготовка СВЕЖЕЙ Ubuntu/Debian к запуску контура мониторинга (#333).
#
# Ставит хостовые предпосылки, которых нет на голой системе: Docker + плагин
# compose v2, Python 3, git, curl. После этого контур поднимается одной командой
# через scripts/bootstrap.sh.
#
# Запуск (из каталога репозитория, под root):
#   sudo bash scripts/install.sh
#
# «С нуля» одной строкой (фрешевая Ubuntu):
#   sudo apt-get update && sudo apt-get install -y git \
#     && git clone https://github.com/Rivega42/autom_for_varnaev monitoring \
#     && cd monitoring && sudo bash scripts/install.sh && scripts/bootstrap.sh --demo
#
# Идемпотентно: повторный запуск не ломает уже установленное.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[0] Проверки окружения"
if [ "$(id -u)" -ne 0 ]; then
  echo "    Требуются права root. Запустите: sudo bash scripts/install.sh" >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "    Скрипт рассчитан на Debian/Ubuntu (apt-get не найден)." >&2
  echo "    На другой ОС установите вручную: Docker + compose v2, Python 3, git." >&2
  exit 1
fi

echo "[1] Системные пакеты (git, curl, python3)"
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 python3-venv

echo "[2] Docker + плагин compose v2"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "    Docker и compose v2 уже установлены — пропуск"
else
  # Официальный convenience-скрипт Docker ставит docker-ce и плагин compose.
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "[3] Доступ к Docker без sudo для пользователя"
# Чтобы scripts/bootstrap.sh запускался без sudo. Группа применится после
# повторного входа в систему (или newgrp docker).
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  usermod -aG docker "$SUDO_USER"
  echo "    Пользователь $SUDO_USER добавлен в группу docker (нужен повторный вход)"
fi

echo
echo "Готово. Версии:"
docker --version
docker compose version | head -1
python3 --version

echo
echo "Дальше — поднять контур одной командой:"
echo "  scripts/bootstrap.sh --demo    # демо без железа (данные идут сами)"
echo "  scripts/bootstrap.sh           # боевой режим (нужны ассеты объекта)"
echo
echo "После старта:"
echo "  GUI настройки : http://localhost:8000/ui/"
echo "  Обзор объекта : http://localhost:8000/ui/overview.html"
echo "  Grafana       : http://localhost:3000"
echo
echo "Если 'docker' требует sudo — перелогиньтесь (группа docker) или: newgrp docker"
