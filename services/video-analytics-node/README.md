# video-analytics-node — серверный воркер на едином ядре

Серверная видеоаналитика, использующая **тот же** движок, что и браузер —
`services/analysis-core`. Цель эпика #241: убрать расхождение между PoC
(браузер) и серверным анализом (раньше — отдельные Python-детекторы). Теперь
логика распознавания одна на всех.

## Что уже есть (проверяемо Node-тестами)

- **`src/runner.mjs`** — оркестратор конвейера: кадры → `AnalysisEngine` →
  события журнала. Источник кадров и приёмник событий **инъектируются**, поэтому
  ядро конвейера детерминировано и покрыто тестами без MediaPipe/сети.
- **`src/payload.mjs`** — преобразование событий движка в события единого журнала
  в той же форме, что у Python-воркера (`action_detected`, `coverage_report`),
  чтобы не ломать `docs/03_API_CONTRACT.md` и дашборды Grafana. Наружу уходят
  только **действия** и **отчёты о покрытии** (позы/лампы — нет, как в браузере).
- **`src/sources.mjs`** — интерфейс источника кадров + `arrayFrames` (для тестов).

## Воспроизведение записи браузера (проверяемо, без MediaPipe/RTSP)

`bin/analyze.mjs` — CLI, прогоняющий **запись** браузерного «Живого анализа»
(кнопка «запись» в `live.html` выгружает `skeleton-*.json`) через ТО ЖЕ
серверное ядро и выдающий события журнала. Замыкает цикл «записал в браузере →
проверил на сервере тем же кодом», не требуя камеры/нативных зависимостей.

```bash
# события в stdout (JSON-строки):
node bin/analyze.mjs --recording skeleton-*.json --room room-01 --zones zones.json
# или сразу в журнал:
node bin/analyze.mjs --recording skeleton-*.json --room room-01 \
     --camera <uuid> --post http://log-service:8000
```

`--zones` принимает и формат API (`GET /cameras/{id}/zones`), и формат ядра.

## Живой воркер (Фаза 3, #255)

- **`src/ffmpeg.mjs`** — сырые кадры из RTSP/видеофайла: ffmpeg дочерним
  процессом, rawvideo/rgba фиксированного размера (640×360), нарезка по границе
  кадра, лимит кадров для бесконечного RTSP.
- **`src/mediapipe.mjs`** — MediaPipe PoseLandmarker в чистом Node: тот же
  `@mediapipe/tasks-vision` (версия зафиксирована = браузерной), WebGL через
  headless-gl (`gl`) с GLES3-шимом. Рецепт выработан спайком на хосте; каждый
  `detect` застрахован таймаутом (известное зависание tasks-vision в Node).
- **`src/queue.mjs`** — протокол очереди `analysis_tasks`, бит-в-бит как у
  Python-воркера: claim через `FOR UPDATE SKIP LOCKED` в одной транзакции
  (безопасно работает ПАРАЛЛЕЛЬНО Python-воркеру), done/failed, heartbeat
  (`video-analytics-node` — своё имя, watchdog различает воркеры).
- **`src/worker.mjs`** — цикл: heartbeat → claim → кадры → ядро → события →
  done/failed; мягкая остановка по SIGTERM между заданиями.
- **`bin/worker.mjs`** — боевая точка входа (pg + MediaPipe + log-service).

Запуск на объекте — профиль compose (параллельно Python-воркеру, очередь общая):

```bash
docker compose --profile node-analytics up -d --build video-analytics-node
```

Ограничения до вывода Python-детекторов (#255 шаг 3): события —
`action_detected`/`coverage_report` (ядро PoC); `uniform_violation` и
присутствие/запретные зоны остаются за Python-воркером; скриншот-артефакт
не сохраняется (`result.artifact = null`).

## Самопроверка живого конвейера (на объекте)

`bin/selfcheck.mjs` — прогон полной цепочки ffmpeg → MediaPipe → ядро без
отправки событий (только сводка и JSON в stdout). Гонять внутри образа:

```bash
# синтетическое видео (без камеры): проверка, что конвейер жив
docker compose --profile node-analytics run --rm -T --entrypoint bash video-analytics-node \
  -c "ffmpeg -f lavfi -i testsrc=duration=10:size=640x360:rate=5 -pix_fmt yuv420p /tmp/t.mp4 -y -loglevel error \
      && bash docker-entrypoint.sh node bin/selfcheck.mjs /tmp/t.mp4 --frames 30"

# живая камера через ретранслятор go2rtc:
docker compose --profile node-analytics run --rm -T \
  video-analytics-node node bin/selfcheck.mjs rtsp://media-gateway:8554/cam-01 --frames 50
```

> Не используйте `xvfb-run` внутри контейнера: как PID 1 он зависает, не
> запустив команду (см. комментарий в `docker-entrypoint.sh`).

## Тесты

```bash
cd services/video-analytics-node
node --test
```

Тесты не требуют Postgres/ffmpeg/MediaPipe — всё инъектируется фейками
(CI гоняет их без `npm install`; `pg`/`gl`/`tasks-vision` ставятся только в
образе воркера).
