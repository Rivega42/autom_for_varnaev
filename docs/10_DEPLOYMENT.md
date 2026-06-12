# 10 · Развёртывание (deployment)

Пошаговое первичное развёртывание контура на сервере объекта. Состав и
взаимодействие — [`docs/diagrams/06_components.md`](diagrams/06_components.md) и
[`07_interactions.md`](diagrams/07_interactions.md). Повседневная эксплуатация
(бэкап, перезапуск, артефакты, логи) — [`docs/09_OPERATIONS.md`](09_OPERATIONS.md).

---

## 0. Быстрый старт (одной командой)

Для нетерпеливых и для тестирования. Подробные ручные шаги — в разделах ниже.

**Демо без железа** — поднять весь контур с *синтетическими* данными датчиков
(данные и события идут сами, видны в Grafana; видеоаналитика отключена — в демо
нет камер и модели):

```bash
scripts/bootstrap.sh --demo
# то же вручную:
# docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Через ~10–60 с в Grafana (http://localhost:3000) появятся ряды показаний, а в
журнале — события порогов (демо периодически выдаёт «всплески»). GUI настройки —
http://localhost:8000/ui/.

**Боевой запуск на объекте** — `.env`, модель видеоаналитики и справочники
заводятся автоматически (справочники — из `db/seeds/object.yaml`, если он есть):

```bash
scripts/bootstrap.sh
```

> Боевой режим всё равно требует *реальных* ассетов объекта: адреса камер в
> `media-gateway/go2rtc.yaml` и прошитые узлы датчиков (ESPHome). Без них стек
> поднимется, но данные пойдут только после подключения оборудования.

---

## 1. Требования

- **Сервер на объекте**: Linux x86-64, Docker + Docker Compose v2.
  Для видеоаналитики на нескольких камерах — несколько ядер CPU (GPU не нужен).
- **Сеть LAN**: узлы датчиков (ESP32-C3) и камеры в одной сети с сервером.
- **Для разработки/проверок** (необязательно на сервере): Python 3.12.

---

## 2. Получить код

```bash
git clone <repo-url> monitoring && cd monitoring
```

---

## 3. Настроить окружение (`.env`)

```bash
cp .env.example .env
```

Обязательно задайте секреты (не оставляйте `change-me`):

| Переменная | Назначение |
|---|---|
| `POSTGRES_PASSWORD` | пароль основного пользователя БД |
| `POSTGRES_RO_PASSWORD` | пароль read-only пользователя Grafana |
| `API_KEY` | значение заголовка `X-API-Key` для `api-gateway` |
| `GF_SECURITY_ADMIN_PASSWORD` | пароль администратора Grafana |

Остальные переменные имеют рабочие значения по умолчанию — полный список с
комментариями в [`.env.example`](../.env.example). Секреты в репозиторий не
кладём (`.env` в `.gitignore`).

---

## 4. Подготовить ассеты объекта

### 4.1 Модель MediaPipe (обязательно для видеоаналитики)
Скачайте официальную модель `PoseLandmarker` и положите файл:
```
models/pose_landmarker.task
```
Без файла воркер `video-analytics` не стартует (см. [`models/README.md`](../models/README.md)).

### 4.2 Камеры (`media-gateway`)
Создайте конфиг медиа-шлюза из примера и опишите RTSP/ONVIF-камеры объекта:
```bash
cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml
```
`go2rtc.yaml` — в `.gitignore` (RTSP-URL содержат пароли камер, в репозиторий
они не попадают); в репозитории — только
[`go2rtc.yaml.example`](../media-gateway/go2rtc.yaml.example).

### 4.3 Расписания видеоанализа (`scheduler`)
```bash
cp config/schedules.example.json config/schedules.json
```
Отредактируйте записи (`source_ref`, `room_id`, `camera_id`, `interval_min`).
`camera_id` нужен, чтобы видеоаналитика считала % покрытия ROI-зон камеры.
Без файла планировщик работает вхолостую (см. [`config/README.md`](../config/README.md)).

---

## 5. Поднять стек

```bash
docker compose up -d
```

Compose сам выдержит порядок (см. [`07_interactions.md` §D](diagrams/07_interactions.md)):

1. `db` (TimescaleDB) — init-скрипты включают расширение `timescaledb` и создают
   read-only пользователя Grafana;
2. `migrate` (one-shot) — `alembic upgrade head` создаёт все прикладные таблицы;
3. прикладные сервисы стартуют только после успешных миграций
   (`service_completed_successfully`).

Проверить состояние:
```bash
docker compose ps          # все healthy / migrate — exited (0)
docker compose logs -f migrate   # «running upgrade … 0011 …»
```

---

## 6. Завести справочники объекта

Помещения, узлы датчиков и камеры заводятся через **веб-GUI** (`/ui/`) или REST —
**без SQL и без прямого доступа к БД** (БД намеренно не публикуется наружу). Порядок:
помещения → узлы датчиков → камеры (узел и камера ссылаются на помещение).

> **Важно:** без узла в справочнике `ingest-sensors` **отбрасывает** показания
> этого датчика (неизвестный узел). Заведите узлы до приёма показаний.

В GUI `/ui/` (введите `API_KEY` в шапке → «Загрузить камеры»): раздел
«Справочники объекта» — формы помещений и узлов; ниже — заведение камер. То же по REST
(`docs/03_API_CONTRACT.md` §3.4a, §3.5):

```bash
H="X-API-Key: $API_KEY"; U=http://localhost:8000/api/v1
curl -X POST -H "$H" $U/rooms        -d '{"id":"room-01","name":"Кухня","is_cold":false}'
curl -X POST -H "$H" $U/sensor-nodes -d '{"id":"node-01","room_id":"room-01"}'
curl -X POST -H "$H" $U/cameras      -d '{"room":"room-01","name":"cam-01","rtsp_url":"rtsp://camera.local/stream"}'
```

> **Массовый импорт (опционально).** Для большого объекта справочники **и пороги
> датчиков** можно загрузить пачкой из YAML одноразовым сервисом `seed` (профиль
> `seed`). Конфиг поддерживает секцию `thresholds` (см. `object.example.yaml`) —
> так алертинг поднимается «из коробки», а не только через GUI. Сервис работает
> **внутри сети контура** (БД наружу не публикуется), идемпотентен (справочники —
> UPSERT по id, пороги — вставка без дублей) и ждёт готовности миграций:
>
> ```bash
> cp db/seeds/object.example.yaml db/seeds/object.yaml   # отредактировать под объект
> docker compose --profile seed run --rm seed            # dry-run: разбор и проверка
> docker compose --profile seed run --rm seed --apply    # запись в БД
> ```
>
> `object.yaml` не коммитится (в `.gitignore`). Прямой запуск `scripts/seed.py`
> с хоста к `localhost:5432` не сработает — порт БД наружу не публикуется.

> **ROI-зоны и тумблеры аналитики** настраиваются по REST через `api-gateway`
> (`docs/03_API_CONTRACT.md` §3.5): `POST /api/v1/cameras/{id}/zones` — добавить
> зону покрытия; `PATCH /api/v1/cameras/{id}` — включить/выключить камеру и
> отдельные функции (`pose`/`actions`/`uniform`/`coverage`). Без зон аналитика
> работает, просто не эмитит `coverage_report`.

> **Пороги датчиков и расписания видеоанализа** настраиваются в веб-GUI (`/ui/`)
> или по REST (`docs/03_API_CONTRACT.md` §3.6) — **без SQL и без правки файлов**.
> Пороги нужны для событий `threshold_exceeded`/`back_to_normal`; расписания —
> «таймер» периодического анализа. Сервисы перечитывают их сами (пороги — раз в
> минуту, расписания — каждый тик). Файл `config/schedules.json` остаётся как
> легаси-вариант (записи БД имеют приоритет).

---

## 7. Проверка работоспособности (smoke)

```bash
# REST-вход (конверт ответа), нужен X-API-Key
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/health

# Разъёмы АУРА в v1 заглушены:
curl -i -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/integration/events   # 501

# Дашборды
xdg-open http://localhost:3000     # вход admin / GF_SECURITY_ADMIN_PASSWORD

# GUI настройки видеоаналитики (камеры, тумблеры функций, разметка ROI мышью)
xdg-open http://localhost:8000/ui/ # введите API_KEY в шапке, «Загрузить камеры»

# Обзор объекта — экран дежурного (помещения, узлы/камеры, лента событий)
xdg-open http://localhost:8000/ui/overview.html   # тот же API_KEY
```

В GUI: выберите камеру → включите/выключите функции аналитики и сохраните →
«Загрузить кадр» (тянется от go2rtc) → кликами обведите ROI-зону → «Сохранить
зону». Зоны и тумблеры сразу учитываются воркером при следующем задании.

Сенсорика: подайте тестовое MQTT-сообщение (формат — [`docs/08_MQTT_CONTRACT.md`](08_MQTT_CONTRACT.md)),
убедитесь, что появилась строка в `sensor_readings` и (при превышении порога) событие в `events`.

---

## 8. Прошивка узлов датчиков

Эталонные конфиги ESPHome — в [`firmware/esphome/`](../firmware/esphome/):
`node.example.yaml` (обычный узел) и `cold_chamber.example.yaml` (холодильная
камера: контроллер снаружи, датчики внутри на I²C-шлейфе). Скопируйте под узел,
задайте Wi-Fi/MQTT, прошейте через ESPHome.

---

## 9. Закрытые сборки (профиль release)

По умолчанию работают читаемые dev-образы. Закрытые (Nuitka + distroless) собираются
профилем `release` (см. [`docs/05_SECURITY_CODE_PROTECTION.md`](05_SECURITY_CODE_PROTECTION.md)):

```bash
docker compose --profile release build
```
Не запускайте release-вариант одновременно с dev-двойником (один порт).

---

## 10. Обновление версии

```bash
git pull
docker compose build                 # пересобрать образы
docker compose run --rm migrate      # применить новые миграции
docker compose up -d                 # перезапустить сервисы
```

---

## 11. Дальше — эксплуатация

Бэкап/восстановление БД, перезапуск, чистка артефактов, логи и тома —
[`docs/09_OPERATIONS.md`](09_OPERATIONS.md).
