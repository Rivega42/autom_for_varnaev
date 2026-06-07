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
metric       text NOT NULL                 -- "air_temp" | "humidity" | "surface_ir"
value        double precision NOT NULL
unit         text NOT NULL                 -- "C" | "%" | "C"
```
- Создаётся как hypertable: `SELECT create_hypertable('sensor_readings','ts');`
- Индекс по `(room_id, metric, ts DESC)` для дашбордов.
- Политика хранения/сжатия — задаётся отдельным issue (зависит от регламента
  заказчика по сроку хранения; см. открытые вопросы решения по датчикам).

Метрики v1: `air_temp` (°C), `humidity` (%), `surface_ir` (°C — бесконтактная
температура поверхности, MLX90614).

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

Типы аналитики соответствуют движку PoC (`07_VIDEO_ANALYTICS.md`): `pose_event` —
простые позы (рука/колено/голова/корпус); `action_detected` — составные действия
(протирание/махи/хлопок/ходьба) с длительностью; `coverage_report` — % покрытия
ROI-зоны; `condition_flagged` — форма («белый халат», цветовая эвристика).

`sensor_silent` критичен для холодовой цепи: молчащий узел = потенциально
испорченный товар. Порог «тишины» — в `thresholds`/конфиге.

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
enabled       boolean DEFAULT true
```

### camera_zones
```
id            serial PRIMARY KEY
camera_id     uuid REFERENCES cameras(id)
zone_type     text NOT NULL        -- "table" | "floor" | "window"
polygon       jsonb NOT NULL       -- вершины ROI-полигона (нормированные)
note          text
```
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
