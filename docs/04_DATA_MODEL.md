# 04 · Модель данных

БД одна — **TimescaleDB** (PostgreSQL 16 + расширение `timescaledb`). Она держит и
временные ряды (показания датчиков), и реляционные сущности (события, задания,
артефакты). Миграции — Alembic (`db/migrations/`).

---

## 1. Обзор сущностей

| Таблица | Тип | Назначение |
|---|---|---|
| `rooms` | справочник | помещения объекта |
| `sensor_nodes` | справочник | узлы датчиков (контроллеры) |
| `sensor_readings` | **hypertable** | временной ряд показаний |
| `cameras` | справочник | камеры по помещениям (RTSP, ракурс/viewpoint) |
| `camera_zones` | конфиг | ROI-зоны камеры (стол/пол/окно) для % покрытия |
| `events` | реляционная | единый журнал событий |
| `analysis_tasks` | реляционная | задания на видеоанализ |
| `artifacts` | реляционная | файлы-доказательства (скриншоты, keypoints; в v2 — видео) |
| `thresholds` | конфиг | пороги для метрик по помещениям |

---

## 2. Справочники

### rooms
```
id           text PRIMARY KEY      -- "room-01"
name         text NOT NULL         -- человекочитаемое имя
is_cold      boolean DEFAULT false -- холодильная/морозильная камера
```

### sensor_nodes
```
id           text PRIMARY KEY      -- "node-01"
room_id      text REFERENCES rooms(id)
placement    text                  -- "снаружи камеры (радио)", "внутри (I2C)" и т.п.
power        text                  -- "mains" | "battery"
note         text
```

---

## 3. Временной ряд показаний

### sensor_readings (hypertable по `ts`)
```
ts           timestamptz NOT NULL          -- момент измерения (UTC)
node_id      text REFERENCES sensor_nodes(id)
room_id      text REFERENCES rooms(id)
metric       text NOT NULL                 -- "air_temp"|"humidity"|"surface_ir"|"uv_index"|"uv_c"
value        double precision NOT NULL
unit         text NOT NULL                 -- "C" | "%" | "C"
```
- Создаётся как hypertable: `SELECT create_hypertable('sensor_readings','ts');`
- Индекс по `(room_id, metric, ts DESC)` для дашбордов.
- Сжатие сырья (lossless) — политика `add_compression_policy` старше
  `READINGS_COMPRESS_AFTER_DAYS` дней (по умолчанию 7); retention
  `add_retention_policy` — `READINGS_RETENTION_DAYS` (0 = выключено, значения по
  регламенту заказчика, #41). Миграция 0018 (#295).

### sensor_readings_hourly (continuous aggregate, #295)
Почасовая свёртка для быстрых дашбордов на длинных рядах (Grafana читает свёртку,
а не сырьё): `bucket` (час), `room_id`, `metric`, `unit`, `avg_value`,
`min_value`, `max_value`. Обновляется политикой раз в час. Сырьё остаётся для
коротких диапазонов и детализации.

Метрики v1: `air_temp` (°C), `humidity` (%), `surface_ir` (°C — бесконтактная
температура поверхности, MLX90614), `uv_index` (общий УФ-индекс/УФ-A, LTR390),
`uv_c` (бактерицидный УФ-C 254 нм, мВт/см², GUVC-S10GD — контроль кварцевых ламп).

---

## 4. Единый журнал событий

### events
```
id            uuid PRIMARY KEY
ts            timestamptz NOT NULL
source        text NOT NULL        -- "sensors" | "analytics"
type          text NOT NULL        -- см. ниже
room_id       text REFERENCES rooms(id)
severity      text NOT NULL        -- "info" | "warning" | "critical"
message       text NOT NULL        -- человекочитаемый текст для оператора (RU)
payload       jsonb NOT NULL       -- машинные детали, зависят от type
artifact_id   uuid REFERENCES artifacts(id)   -- NULL, если артефакта нет
task_id       uuid REFERENCES analysis_tasks(id) -- если событие от задания
```

`message` — готовая фраза на русском с контекстом помещения, которую формирует
источник события (`ingest-sensors`/`video-analytics`) в момент создания. Адресована
оператору (журнал, дашборд, API) и **не подменяет** машинный `payload`. Миграция
таблицы `events` (E1.9) включает колонку `message`.

**Типы событий (стартовый набор):**

| source | type | payload (пример) | message (пример, RU) |
|---|---|---|---|
| sensors | `threshold_exceeded` | `{"metric":"air_temp","value":8.7,"threshold":8.0}` | «В холодильной камере температура выше нормы» |
| sensors | `sensor_silent` | `{"node_id":"node-03","silent_for_min":12}` | «Датчик в холодильной камере молчит 12 минут» |
| sensors | `back_to_normal` | `{"metric":"humidity"}` | «В помещении для приготовления пищи влажность вернулась к норме» |
| analytics | `pose_event` | `{"pose":"right_arm_up","limb":"right_arm"}` | «Поднята правая рука» |
| analytics | `action_detected` | `{"action":"surface_wiped","hands":"both","duration_s":4.2}` | «Протирание поверхности двумя руками, 4 с» |
| analytics | `coverage_report` | `{"zone":"table","zone_id":7,"coverage_pct":63}` | «Покрытие зоны стола — 63%» |
| analytics | `condition_flagged` | `{"flag":"no_uniform","brightness":0.4,"saturation":0.5}` | «Не распознана спецодежда (белый халат)» |
| analytics | `uniform_violation` | `{"flag":"no_uniform","duration_s":7.0,"brightness":0.4,"saturation":0.5}` | «Человек без спецодежды (белого халата) дольше 7 с» |
| analytics | `forbidden_zone_entry` | `{"zone_id":3}` | «Человек в запретной зоне» |
| analytics | `presence_detected` | `{"zone_id":4}` | «Зафиксировано присутствие в рабочей зоне» |
| analytics | `presence_missing` | `{"rule_id":1,"window":"08:00–17:00","absent_for_min":35}` | «В помещении Цех приготовления нет присутствия в рабочей зоне 35 мин (окно 08:00–17:00, допустимо 30 мин)» |
| analytics | `cleaning_overdue` | `{"zone":"table","reason":"не убиралась более 4 ч (прошло 5.2 ч)"}` | «Зона «стол» (помещение room-01): не убиралась более 4 ч» |
| analytics | `camera_offline` | `{"camera_id":"...","camera_name":"Кухня-1"}` | «Камера «Кухня-1» в Цех приготовления не отвечает» |
| analytics | `camera_online` | `{"camera_id":"...","camera_name":"Кухня-1"}` | «Камера «Кухня-1» в Цех приготовления снова на связи» |
| analytics | `media_gateway_offline` | `{"service":"media-gateway"}` | «Медиа-шлюз камер (go2rtc) недоступен — состояние камер неизвестно» |
| analytics | `media_gateway_online` | `{"service":"media-gateway"}` | «Медиа-шлюз камер (go2rtc) снова на связи» |
| analytics | `service_silent` | `{"service":"ingest-sensors","silent_for_min":12}` | «Сервис «ingest-sensors» не отвечает 12 мин» |
| analytics | `service_restored` | `{"service":"ingest-sensors"}` | «Сервис «ingest-sensors» снова на связи» |

Типы аналитики соответствуют движку PoC (`07_VIDEO_ANALYTICS.md`): `pose_event` —
простые позы (рука/колено/голова/корпус); `action_detected` — составные действия
(протирание/махи/хлопок/ходьба) с длительностью; `coverage_report` — % покрытия
ROI-зоны; `condition_flagged` — форма («белый халат», цветовая эвристика).
`uniform_violation` (#272) — то же по правилу: человек без признака халата дольше
`ANALYTICS_UNIFORM_MIN_S` секунд → событие (раз на эпизод) со стоп-кадром. Это
эвристика (яркость/насыщенность торса), а не обученный детектор СИЗ (см. #105).

`sensor_silent` критичен для холодовой цепи: молчащий узел = потенциально
испорченный товар. Порог «тишины» — в `thresholds`/конфиге.

`camera_offline`/`camera_online` — живость камер (#283), симметрично «тишине»
узла датчика. Планировщик на каждом тике пробует кадр камеры у go2rtc
(`/api/frame.jpeg?src=<имя камеры>`); отвал даёт `camera_offline` один раз на
эпизод, восстановление — `camera_online`. Имя потока в go2rtc = `cameras.name`.

`media_gateway_offline`/`media_gateway_online` — живость самого медиа-шлюза
(#286). Перед покамерными пробами планировщик проверяет API go2rtc (`GET /api`);
если шлюз недоступен, вместо лавины `camera_offline` по всем камерам эмитится
один агрегированный сигнал (раз на эпизод), покамерные эпизоды замораживаются
до восстановления шлюза.

`service_silent`/`service_restored` — живость наших сервисов (watchdog, #284).
Каждый ключевой сервис (`ingest-sensors`, `scheduler`, `video-analytics`)
периодически обновляет свою строку в `service_heartbeats`; планировщик читает её
и, если сервис «замолчал» дольше `SERVICE_SILENT_MIN` минут, эмитит
`service_silent` (раз на эпизод), при возвращении — `service_restored`.

### service_heartbeats (живость сервисов, #284)
```
service  text PRIMARY KEY     -- имя сервиса (ingest-sensors | scheduler | video-analytics)
ts       timestamptz NOT NULL -- время последнего heartbeat (UPSERT по service)
meta     jsonb                -- зарезервировано (детали сервиса), пока NULL
```
Каждый сервис обновляет свою строку в своём цикле (UPSERT `ON CONFLICT(service)`).
Планировщик читает таблицу и сверяет свежесть с порогом `SERVICE_SILENT_MIN`.

---

## 5. Задания на анализ

Сущность первого класса уже в v1 (планировщик создаёт по расписанию; в v2 —
ещё и АУРА по REST). Единый механизм, разные триггеры.

### analysis_tasks
```
id            uuid PRIMARY KEY
created_at    timestamptz NOT NULL
source_type   text NOT NULL        -- "stream" | "file"
source_ref    text NOT NULL        -- RTSP URL или путь к файлу на томе
room_id       text REFERENCES rooms(id)
camera_id     uuid REFERENCES cameras(id)  -- камера задания: по ней берутся ROI-зоны (% покрытия)
pipeline      text NOT NULL        -- "pose_v1" и т.п.
params        jsonb                -- параметры пайплайна (fps и пр.)
status        text NOT NULL        -- см. ниже
trigger       text NOT NULL        -- "schedule" | "aura" | "manual"
started_at    timestamptz
finished_at   timestamptz
result        jsonb                -- сводка результата (счётчики, ссылки)
error         text                 -- если status=failed
callback_url  text                 -- v2: webhook о готовности (СТЫК-АУРА)
```

**Статусы (жизненный цикл):**
```
queued ─► running ─► done
                └──► failed
queued ─► cancelled
```
Диаграмма жизненного цикла — `docs/diagrams/04_task_lifecycle.bpmn`.

В v1 `trigger` принимает `schedule` и `manual`; значение `aura` зарезервировано
(`# СТЫК-АУРА (v2)`).

---

## 6. Артефакты

Скриншот (v1) и видеофайл (v2) — один тип записи. Файл лежит на общем томе, в БД —
метаданные и путь.

### artifacts
```
id            uuid PRIMARY KEY
created_at    timestamptz NOT NULL
kind          text NOT NULL        -- "screenshot" | "keypoints" | "coverage" | "video"
path          text NOT NULL        -- "/data/artifacts/2026-06-05/<id>.jpg"
mime          text
room_id       text REFERENCES rooms(id)
camera_id     uuid REFERENCES cameras(id)         -- если артефакт с камеры
task_id       uuid REFERENCES analysis_tasks(id)  -- если получен заданием
meta          jsonb
```
Путь — по схеме `/data/artifacts/<YYYY-MM-DD>/<id>.<ext>` (см. `01_ARCHITECTURE.md` §6).

---

## 6a. Камеры и ROI-зоны

Камеры привязаны к помещениям; ROI-зоны и ракурс — это конфиг, который PoC
экспортировал в JSON (см. `07_VIDEO_ANALYTICS.md`), теперь хранится в БД.

### cameras
```
id            uuid PRIMARY KEY
room_id       text REFERENCES rooms(id)
name          text NOT NULL
rtsp_url      text NOT NULL        -- источник для media-gateway
viewpoint     jsonb                -- пресет ракурса из PoC
enabled       boolean DEFAULT true  -- камера активна; false = аналитика выключена
analytics     jsonb                -- тумблеры функций {pose,actions,uniform,coverage}; null = все вкл.
```

> Управление `enabled`/`analytics` и ROI-зонами — через REST `api-gateway`
> (`docs/03_API_CONTRACT.md` §3.5); воркер видеоаналитики учитывает тумблеры.

### camera_zones
```
id            serial PRIMARY KEY
camera_id     uuid REFERENCES cameras(id)
zone_type     text NOT NULL        -- "table" | "floor" | "window" | "forbidden" | "work"
polygon       jsonb NOT NULL       -- вершины ROI-полигона (нормированные)
note          text
```
`forbidden` (#299) — запретная зона: вход репрезентативной точки человека
(середина бёдер/плеч) в полигон → событие `forbidden_zone_entry` (раз на эпизод).
`work` (#302) — рабочая зона: присутствие в ней → `presence_detected` (INFO, раз
на эпизод; основа для оконного алерта присутствия #300). Тумблер обоих —
`cameras.analytics.presence`.
`video-analytics` берёт зоны камеры для расчёта `coverage_report` по типам.

---

## 7. Пороги

### thresholds
```
id            serial PRIMARY KEY
room_id       text REFERENCES rooms(id)   -- NULL = глобально
metric        text NOT NULL
op            text NOT NULL        -- ">" | "<" | ">=" | "<="
value         double precision NOT NULL
severity      text NOT NULL        -- "warning" | "critical"
silent_min    int                  -- порог "тишины" узла, мин (для sensor_silent)
enabled       boolean DEFAULT true
```
`ingest-sensors` сверяет показания с `thresholds` и при срабатывании пишет
`events`. В v2 пороги может присылать АУРА (`PUT /integration/settings`).

### cleaning_rules (санитарный контроль уборки, #265)
```
id               serial PRIMARY KEY
room_id          text NOT NULL REFERENCES rooms(id)
zone_type        text NOT NULL        -- "table" | "floor" | "window" (как camera_zones)
interval_hours   double precision NOT NULL  -- зона должна убираться не реже, чем раз в N ч
min_coverage_pct int NOT NULL DEFAULT 0     -- мин. покрытие последней уборки, %
zone_name        text                 -- подпись для оператора
enabled          boolean DEFAULT true
UNIQUE (room_id, zone_type)
```
Планировщик на каждом тике сверяет правила с последними `coverage_report` по
зоне и при нарушении пишет `cleaning_overdue` (раз на эпизод; эпизод закрывается,
когда зона снова убрана вовремя и с нормальным покрытием).

### presence_rules (контроль присутствия по окну времени, #300)
```
id               serial PRIMARY KEY
room_id          text NOT NULL REFERENCES rooms(id)
window_start     time NOT NULL        -- начало окна (дневное окно: start < end)
window_end       time NOT NULL        -- конец окна
max_absence_min  int NOT NULL DEFAULT 30  -- допустимый перерыв присутствия, мин
enabled          boolean DEFAULT true
UNIQUE (room_id, window_start, window_end)
```
Планировщик на каждом тике сверяет правила с последними `presence_detected`
(#302) по помещению: если внутри окна присутствия нет дольше `max_absence_min`
минут — пишет `presence_missing` (раз на эпизод; эпизод закрывается новым
присутствием или выходом из окна). Времена окна интерпретируются в часовом
поясе `PRESENCE_TZ` планировщика (IANA-имя, по умолчанию UTC); окна через
полночь в v1 не поддерживаются.

---

## 8. Связи (кратко)

```
rooms 1───* sensor_nodes 1───* sensor_readings
rooms 1───* cameras 1───* camera_zones
rooms 1───* events *───0..1 artifacts
cameras 1───* artifacts
cameras 1───* analysis_tasks
rooms 1───* analysis_tasks 1───* artifacts
analysis_tasks 1───* events
rooms 1───* thresholds
```

---

## 9. Что из этого — задачи Кода (эпик E1)

- Включить `timescaledb`, создать `sensor_readings` как hypertable.
- Alembic-миграции на все таблицы §2–§7.
- Сиды справочников `rooms`/`sensor_nodes` из конфига объекта.
- Индексы под дашборды Grafana.
- Pydantic-модели в `shared/` соответствуют таблицам и схемам событий/заданий.
- Политика хранения/сжатия рядов — отдельный issue (ждёт регламент заказчика).
