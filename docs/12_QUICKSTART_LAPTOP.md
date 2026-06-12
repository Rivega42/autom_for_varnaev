# 12 · Быстрый старт на ноутбуке

Запуск контура мониторинга на ноутбуке для проверки. Два сценария: **демо** без
железа (данные генерируются сами) и **с реальными камерами** (видеоаналитика по
RTSP). Полное развёртывание на сервере объекта — [`docs/10_DEPLOYMENT.md`](10_DEPLOYMENT.md).

## Требования

- **Docker + Docker Compose v2** (Docker Desktop на Windows/macOS или Docker Engine на Linux).
- **Интернет при первом запуске** — тянутся базовые образы и собираются наши (несколько минут).
- Свободные порты на хосте: **8000** (API/GUI), **3000** (Grafana), **1883** (MQTT).
- Python 3.12 — только чтобы запустить `scripts/*.py` с хоста (генерация `.env`, модель).

---

## Сценарий A. Демо без железа (синтетические датчики)

Поднимает весь контур и сам генерирует поток показаний; видеоаналитика отключена
(в демо нет камер и модели). Данные и события видны через ~10–60 с.

```bash
scripts/bootstrap.sh --demo
# то же вручную:
# python scripts/init_env.py
# docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Открыть:
- **Grafana** — http://localhost:3000 (логин `admin`, пароль — из `.env`, ключ `GF_SECURITY_ADMIN_PASSWORD`): ряды показаний и события порогов.
- **GUI настройки** — http://localhost:8000/ui/ (поле `X-API-Key` — из `.env`, ключ `API_KEY`).
- **Обзор объекта (экран дежурного)** — http://localhost:8000/ui/overview.html
  (тот же ключ; помещения с показаниями, статусы узлов/камер, лента событий, автообновление).
- **API** — http://localhost:8000/api/v1/health.

Остановить: `docker compose -f docker-compose.yml -f docker-compose.demo.yml down`
(добавить `-v`, чтобы стереть и данные).

---

## Сценарий B. С реальными камерами (видеоаналитика по RTSP)

Здесь нужен **боевой стек** (с `video-analytics`), модель MediaPipe и адреса
камер. Демо-оверлей НЕ используется (он глушит видео).

### Шаг 1. Модель видеоаналитики (обязательно)

```bash
bash scripts/fetch_model.sh        # скачает models/pose_landmarker.task
```
Без файла модели воркер `video-analytics` не стартует. Вариант модели можно
переопределить переменной `ANALYTICS_MODEL_URL` (см. [`models/README.md`](../models/README.md)).

### Шаг 2. Адреса камер в go2rtc

Создайте конфиг из примера и пропишите свои потоки (`go2rtc.yaml` — в
`.gitignore`: пароли камер в репозиторий не попадают):

```bash
cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml
```

**Имя потока** (ключ) должно
совпадать с именем камеры в справочнике — по нему GUI берёт кадр-превью:

```yaml
api:
  listen: ":1984"
streams:
  cam-01: rtsp://ЛОГИН:ПАРОЛЬ@192.168.1.50:554/stream1
  cam-02: rtsp://ЛОГИН:ПАРОЛЬ@192.168.1.51:554/stream1
```
go2rtc ретранслирует каждый поток по RTSP внутри сети контура как
`rtsp://media-gateway:8554/<имя-потока>` — этот адрес и пойдёт в расписание.

### Шаг 3. Запустить боевой стек

```bash
python scripts/init_env.py         # .env со случайными секретами (идемпотентно)
docker compose up -d --build
```
Поднимутся db, migrate, mqtt-broker, log-service, api-gateway, scheduler,
media-gateway, video-analytics, grafana. (ingest-sensors тоже стартует, но без
реальных датчиков просто простаивает — это нормально.)

### Шаг 4. Завести помещение, камеру и расписание (GUI или REST)

В GUI http://localhost:8000/ui/ (введите `API_KEY` в шапке):
1. **Помещение** — напр. `room-01`.
2. **Камера** — `name` = `cam-01` (как в go2rtc.yaml), `rtsp_url` = адрес камеры, помещение `room-01`.
3. **Расписание видеоанализа**:
   - `source_ref` = `rtsp://media-gateway:8554/cam-01` (ретранслятор go2rtc);
   - `pipeline` = `pose_v1`, интервал (мин), камера из п.2.

Те же действия по REST (`docs/03_API_CONTRACT.md`):
```bash
H="X-API-Key: $API_KEY"; U=http://localhost:8000/api/v1
curl -X POST -H "$H" $U/rooms     -d '{"id":"room-01","name":"Цех","is_cold":false}'
curl -X POST -H "$H" $U/cameras   -d '{"room":"room-01","name":"cam-01","rtsp_url":"rtsp://192.168.1.50:554/stream1"}'
curl -X POST -H "$H" $U/schedules -d '{"name":"cam-01-pose","source_ref":"rtsp://media-gateway:8554/cam-01","pipeline":"pose_v1","camera_id":"<UUID-камеры>","interval_min":5}'
```

### Шаг 5. Где смотреть результат

Планировщик в течение тика создаст задание, `video-analytics` его обработает:
- **События** анализа — `GET /api/v1/events` и лента событий в **Grafana**;
- **Скриншоты-доказательства** — в томе `artifacts` (см. `docs/09_OPERATIONS.md`);
- **ROI-зоны** для % покрытия размечаются мышью в GUI поверх превью-кадра.

Остановить: `docker compose down` (с `-v` — со стиранием данных).

### Шаг 6. Живой анализ в браузере (скелет/распознавание)

В редакторе камеры — кнопка **«Живой анализ (скелет)»**: открывает страницу, где
поверх живого видео в браузере рисуется скелет позы, распознаётся протирание,
% покрытия зон и ведётся журнал со стоп-кадрами (порт PoC `motion-log.html`).

MediaPipe, WASM и модель отдаются **локально** из api-gateway (без CDN) — их нужно
вендорить ДО сборки образа:
```bash
bash scripts/fetch_web_assets.sh   # качает в static/vendor (~25 МБ); bootstrap.sh делает это сам
docker compose up -d --build       # пересобрать api-gateway, чтобы ассеты попали в образ
```
Камера должна отдавать **H264** (браузеры не играют H265); go2rtc транскодирует
поток в MJPEG для `<img>`. Версии MediaPipe/hls фиксированы в `fetch_web_assets.sh`.

> CI-образы вендоренные ассеты не содержат (это браузерная функция) — на объекте
> их кладёт `bootstrap.sh`/`fetch_web_assets.sh` перед сборкой.

---

## Обновление работающего стека

После `git pull` обычное обновление — `docker compose up -d --build`. Но если в
обновлении менялась **сетевая топология** compose (секция `networks:` — например,
появление сети `edge` и `internal: true`), Docker не перенастраивает сети уже
созданного стека. Тогда обновляйтесь через пересоздание:

```bash
docker compose down          # данные не теряются: тома (БД, артефакты) сохраняются
docker compose up -d --build
```

`docker compose restart` сети тоже **не** обновляет.

## Типовые проблемы

| Симптом | Причина / решение |
|---|---|
| `video-analytics` рестартует | Нет `models/pose_landmarker.task` — выполните `bash scripts/fetch_model.sh`. |
| Контейнер не стартует, ошибка `${VAR:?}` | Нет `.env` — выполните `python scripts/init_env.py`. |
| Порт занят (8000/3000/1883) | Освободите порт или поменяйте маппинг в `docker-compose.yml`. |
| Нет событий по камере | Нет расписания (создайте в GUI) или камера недоступна — проверьте RTSP плеером (VLC) и доступность IP из сети ноутбука. |
| GUI не показывает превью камеры | Имя камеры в справочнике ≠ имя потока в `go2rtc.yaml`, либо неверный RTSP в go2rtc. |
| Показания датчиков не идут | Это ожидаемо без реальных узлов; для проверки сенсорики используйте Сценарий A (демо). |

## Что осмотреть при отладке

```bash
docker compose ps                       # статусы контейнеров
docker compose logs -f video-analytics  # лог воркера видеоаналитики
docker compose logs -f scheduler        # создаёт ли задания
docker compose logs -f media-gateway    # подключение go2rtc к камерам
```
