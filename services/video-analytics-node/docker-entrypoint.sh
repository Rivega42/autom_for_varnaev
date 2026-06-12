#!/usr/bin/env bash
# Виртуальный X-дисплей для headless-gl (WebGL нужен MediaPipe), затем команда.
#
# НАМЕРЕННО не xvfb-run: его протокол готовности X-сервера (SIGUSR1 родителю)
# не работает, когда xvfb-run оказывается PID 1 контейнера, — он зависает,
# не запустив команду (bash tail-exec делает PID 1 из последней команды).
# Поднимаем Xvfb сами и ждём готовности по lock-файлу.
set -e
Xvfb :99 -screen 0 640x480x24 -nolisten tcp >/dev/null 2>&1 &
for _ in $(seq 1 50); do
  [ -e /tmp/.X99-lock ] && break
  sleep 0.1
done
export DISPLAY=:99
exec "$@"
