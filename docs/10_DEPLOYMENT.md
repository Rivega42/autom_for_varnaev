# 10 · Развёртывание (deployment)

Пошаговое первичное развёртывание контура на сервере объекта. Состав и
взаимодействие — [`docs/diagrams/06_components.md`](diagrams/06_components.md) и
[`07_interactions.md`](diagrams/07_interactions.md). Повседневная эксплуатация
(бэкап, перезапуск, артефакты, логи) — [`docs/09_OPERATIONS.md`](09_OPERATIONS.md).

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
Опишите RTSP/ONVIF-камеры объекта в [`media-gateway/go2rtc.yaml`](../media-gateway/go2rtc.yaml).

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

## 6. Засеять справочники

Справочники помещений/узлов/камер засеваются из конфига объекта скриптом
(см. [`db/seeds/object.example.yaml`](../db/seeds/object.example.yaml)):

```bash
cp db/seeds/object.example.yaml db/seeds/object.yaml   # отредактировать под объект
# dry-run (печатает, что вставит):
DATABASE_URL=postgresql+psycopg2://monitoring:$POSTGRES_PASSWORD@localhost:5432/monitoring \
  python scripts/seed.py db/seeds/object.yaml
# применить:
DATABASE_URL=... python scripts/seed.py db/seeds/object.yaml --apply
```

> **ROI-зоны (`camera_zones`)** для расчёта % покрытия заполняются отдельно
> (нормированные полигоны на камеру) — пока вставляются SQL-ом в таблицу
> `camera_zones`. Без зон видеоаналитика работает, просто не эмитит `coverage_report`.

---

## 7. Проверка работоспособности (smoke)

```bash
# REST-вход (конверт ответа), нужен X-API-Key
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/health

# Разъёмы АУРА в v1 заглушены:
curl -i -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/integration/events   # 501

# Дашборды
xdg-open http://localhost:3000     # вход admin / GF_SECURITY_ADMIN_PASSWORD
```

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
