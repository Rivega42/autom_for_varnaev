# 03 · Контракт API (REST / JSON)

Единственная внешняя точка нашего контура — `api-gateway`. Здесь зафиксирован
контракт: общие конвенции, внутренние эндпойнты (v1) и разъёмы для АУРА (заглушены
в v1, включаются в v2).

Диаграмма взаимодействия «кто кому что шлёт» — `docs/diagrams/03_api_collaboration.bpmn`
(+ SVG-превью).

> Машинно-читаемая версия контракта — это OpenAPI, который FastAPI отдаёт на
> `/openapi.json` и `/docs`. При изменении кода контракта **обязательно**
> обновляется и этот документ (правило из `CLAUDE.md` §7).

---

## 1. Общие конвенции

- Базовый префикс: `/api/v1`.
- Формат тела и ответа — **JSON**, кодировка UTF-8.
- Времена — **ISO-8601 в UTC** со суффиксом `Z`: `2026-06-05T10:30:00Z`.
- Бинарь (картинки, видео) **по REST не передаётся.** В JSON — только метаданные
  и путь к файлу на общем томе (`artifact_path`).
- Идентификаторы сущностей — UUID v4 (строкой).
- Аутентификация внутренних вызовов в v1 — по сети `internal` (доверенная). На
  публичных эндпойнтах и на `/integration/*` — API-ключ в заголовке
  `X-API-Key` (значение из `.env`).
- **Роли (#291).** Ключи задаются per-user: `API_KEYS=ключ:роль,ключ:роль`
  (роли `operator`|`admin`); legacy `API_KEY` = роль `admin` (совместимость).
  `operator` — чтение и подтверждение событий (`POST /events/{id}/ack`);
  `admin` — ещё и настройка (POST/PATCH/DELETE справочников, камер, ROI-зон,
  порогов, расписаний, правил уборки; `/integration/*`). Нет/неверный ключ →
  `401 UNAUTHORIZED`; роли недостаточно → `403 FORBIDDEN`. Если ключи не заданы
  вовсе (dev/тесты) — проверка отключена. Медиа-эндпойнты (кадр/видеопоток)
  принимают ключ из заголовка ИЛИ `?api_key=` (для тегов `<img>`), любая роль.

### 1.1 Единый конверт ответа

Все ответы `api-gateway` оборачиваются в один конверт:

**Успех:**
```json
{
  "status": "ok",
  "data": { "...": "полезная нагрузка" },
  "error": null,
  "ts": "2026-06-05T10:30:00Z"
}
```

**Ошибка:**
```json
{
  "status": "error",
  "data": null,
  "error": { "code": "TASK_NOT_FOUND", "message": "Задание не найдено" },
  "ts": "2026-06-05T10:30:00Z"
}
```

Поле `status` — `"ok"` | `"error"`. Конверт описывается один раз в `shared/` и
переиспользуется всеми сервисами.

### 1.2 Коды ошибок (стартовый набор)

| code | HTTP | смысл |
|---|---|---|
| `VALIDATION_ERROR` | 422 | тело запроса не прошло валидацию |
| `UNAUTHORIZED` | 401 | отсутствует или неверен `X-API-Key` |
| `FORBIDDEN` | 403 | ключ валиден, но роли недостаточно (нужна `admin`) |
| `TASK_NOT_FOUND` | 404 | задание с таким id отсутствует |
| `EVENT_NOT_FOUND` | 404 | событие отсутствует |
| `CAMERA_NOT_FOUND` | 404 | камера с таким id отсутствует |
| `ZONE_NOT_FOUND` | 404 | ROI-зона с таким id отсутствует |
| `THRESHOLD_NOT_FOUND` | 404 | порог с таким id отсутствует |
| `SCHEDULE_NOT_FOUND` | 404 | расписание с таким id отсутствует |
| `SCHEDULE_DUPLICATE_NAME` | 409 | расписание с таким именем уже существует (имя — уникальный ключ слота) |
| `ROOM_NOT_FOUND` | 404 | помещение с таким id отсутствует (напр. при заведении узла) |
| `ROOM_ALREADY_EXISTS` | 409 | помещение с таким id уже существует |
| `NODE_ALREADY_EXISTS` | 409 | узел датчиков с таким id уже существует |
| `ARTIFACT_NOT_FOUND` | 404 | артефакт-доказательство с таким id отсутствует (или файл недоступен) |
| `CLEANING_RULE_NOT_FOUND` | 404 | правило контроля уборки с таким id отсутствует |
| `CLEANING_RULE_DUPLICATE` | 409 | правило для этой зоны (помещение+тип) уже существует |
| `PRESENCE_RULE_NOT_FOUND` | 404 | правило контроля присутствия с таким id отсутствует |
| `PRESENCE_RULE_DUPLICATE` | 409 | правило с таким окном для помещения уже существует |
| `LICENSE_LIMIT` | 409 | достигнут лимит тарифа (помещения/камеры/узлы) — нужен лицензионный ключ (#335) |
| `NOT_IMPLEMENTED` | 501 | эндпойнт-разъём АУРА выключен в v1 |
| `INTERNAL` | 500 | прочая внутренняя ошибка |

---

## 2. Карта «кто кому что шлёт»

| Источник | Получатель | Канал | Что |
|---|---|---|---|
| Узел датчика (ESP32) | `mqtt-broker` | MQTT | показание (t°, влажность, ИК) |
| `mqtt-broker` | `ingest-sensors` | MQTT (подписка) | показание |
| `ingest-sensors` | `db` | SQL | запись показания |
| `ingest-sensors` | `log-service` | внутр. REST | событие (порог / «тишина») |
| `scheduler` (v1) | `log-service`/`video-analytics` | внутр. REST | создать задание на анализ |
| `video-analytics` | общий том | файл | скриншот-артефакт |
| `video-analytics` | `log-service` | внутр. REST | событие аналитики (+ путь артефакта) |
| `grafana` | `db` | SQL (ro) | чтение рядов и событий для дашбордов |
| **АУРА (v2)** | `api-gateway` | REST `/integration/*` | задание на анализ файла, чтение событий, настройки |
| **`api-gateway` (v2)** | АУРА | (опц.) webhook | уведомление «задание готово» |

В v1 строки с АУРА не активны (эндпойнты заглушены).

---

## 3. Внутренние / публичные эндпойнты (v1, рабочие)

### 3.1 Здоровье
```
GET /api/v1/health → 200 {"status":"ok","data":{"service":"api-gateway","up":true}}
```

### 3.1a Лицензия (тариф и лимиты, #335)
```
GET /api/v1/license   # текущий тариф, лимиты и расход (для баннера в GUI)
```
`data`: `status` (`demo|active|expired|invalid`), `tier`, `customer`, `expires`,
`limits` (`{rooms, cameras, nodes}`, число или `null` = без ограничения),
`usage` (текущий расход по тем же сущностям). Демо без ключа — лимит 1/1/1.
Заведение сверх лимита (`POST /rooms·/cameras·/sensor-nodes`) → `409
LICENSE_LIMIT`. Расширение — лицензионным ключом (`LICENSE_KEY`, см.
`docs/14_LICENSING.md`). Граница АУРА лицензирования не касается (наш контур).

### 3.2 События (журнал)
```
GET /api/v1/events?from=&to=&type=&room=&limit=&offset=
```
Возвращает список событий журнала (фильтры по времени/типу/помещению).
`data`:
```json
{
  "items": [
    {
      "id": "f1c2...uuid",
      "ts": "2026-06-05T10:30:00Z",
      "source": "sensors",
      "type": "threshold_exceeded",
      "room": "room-01",
      "severity": "warning",
      "message": "В холодильной камере температура выше нормы",
      "payload": { "metric": "air_temp", "value": 8.7, "threshold": 8.0 },
      "artifact_path": null
    }
  ],
  "total": 1
}
```

Поле `message` — готовая фраза на русском для оператора (с контекстом помещения),
`payload` — машинные детали. Источник события формирует `message` при создании
(см. `docs/04_DATA_MODEL.md` §4). В v1 события датчиков выводятся из показаний по
критериям (пороги/«тишина»); сами показания в АУРА не передаются.

В тот же журнал попадают события живости инфраструктуры: `camera_offline`/
`camera_online` (#283) — планировщик пробует кадр камеры у go2rtc и сообщает об
отвале/восстановлении (раз на эпизод), симметрично «тишине» узла датчика;
`media_gateway_offline`/`media_gateway_online` (#286) — недоступность самого
go2rtc даёт один агрегированный сигнал вместо лавины `camera_offline`; и
`service_silent`/`service_restored` (#284) — watchdog следит за свежестью
heartbeat'ов наших сервисов (`ingest-sensors`, `scheduler`, `video-analytics`).

```
GET /api/v1/events/{id} → одно событие
POST /api/v1/events/{id}/ack         → подтвердить событие (эскалация прекращается)
POST /api/v1/analytics-events        → событие браузерного живого анализа в журнал
GET /api/v1/artifacts/{id}           → файл артефакта-доказательства (стоп-кадр/overlay)
```

**Подтверждение и эскалация (#264).** Критичное событие, не подтверждённое
оператором (`POST /events/{id}/ack`, идемпотентно) за `NOTIFY_ESCALATE_AFTER_MIN`
минут, уведомляется повторно через те же каналы (с пометкой «ПОВТОР N»), с паузой
`NOTIFY_ESCALATE_REPEAT_MIN` и максимумом `NOTIFY_ESCALATE_MAX` повторов.
Эскалация выключена по умолчанию (`NOTIFY_ESCALATE_AFTER_MIN=0`). В элементе
события появляется поле `acknowledged_at` (null = не подтверждено).

**Тело `POST /analytics-events`** (от браузерного «Живого анализа», `live.html`):
```json
{ "room": "room-01", "message": "Стол протёрт (правой рукой, 5 с)", "severity": "info",
  "payload": { "camera_id": "…" },
  "image": "data:image/jpeg;base64,…" }
```
Шлюз создаёт событие `source=analytics`, добавляя в `payload` метку
`origin=browser` (отличить от серверного анализа по расписанию), и пишет его в
log-service. Так распознавания из браузера попадают в Grafana.

Поле `type` — из белого списка: `action_detected` (по умолчанию) или
`coverage_report`. Для отчёта о покрытии браузер шлёт тот же payload, что и
серверный воркер:
```json
{ "room": "room-01", "message": "стол протёрт на 80%", "type": "coverage_report",
  "payload": { "zone": "table", "zone_id": 7, "coverage_pct": 80 } }
```
Тип вне списка → 422 `VALIDATION_ERROR`.
Поле `image` необязательно: если задан стоп-кадр (data-URL), шлюз сохраняет его
как артефакт-скриншот, а событие получает `artifact_id` и `payload.artifact_url`
(`/api/v1/artifacts/{id}`) — чтобы кадр был виден в Grafana. Ответ `data`:
`{ "id": "…", "artifact_id": "…"|null }`.

**`GET /artifacts/{id}`** отдаёт сам файл артефакта (`image/jpeg`/`image/png`, не
конверт) — стоп-кадры и heat-overlay протирки для Grafana/GUI. Метаданные берутся
из таблицы `artifacts`, файл читается с общего тома (только внутри каталога
артефактов). Ключ принимается в заголовке `X-API-Key` ИЛИ в `?api_key=` (чтобы
кадр грузился тегом `<img>`). Нет артефакта/файла → 404 `ARTIFACT_NOT_FOUND`.

### 3.3 Задания на анализ
```
POST /api/v1/analysis-tasks
```
Тело:
```json
{
  "source_type": "stream",          // "stream" | "file"
  "source_ref": "rtsp://cam-01/...",// URL потока ИЛИ путь к файлу на томе
  "room": "room-01",
  "camera_id": "…",                 // опц.: по нему применяются настройки камеры
  "pipeline": "pose_v1",            // какой анализ применить
  "params": { "fps": 5 }
}
```
Ответ `data`: созданное задание со `status: "queued"` и `id`. Если задан
`camera_id`, воркер применит к заданию тумблеры аналитики и ROI-зоны этой камеры
— одинаково для `stream` и `file` (распознавание по переданному файлу).

```
GET /api/v1/analysis-tasks/{id}       → статус и результат задания
GET /api/v1/analysis-tasks?status=&from=&to=  → список
```
Сущность задания и статусы — `docs/04_DATA_MODEL.md`.

### 3.4 Показания датчиков (для интеграций/проверки; основной путь — Grafana)
```
GET /api/v1/readings?room=&metric=&from=&to=&limit=
```

### 3.4a Справочники объекта: помещения и узлы датчиков

Базовые справочники заводятся через интерфейс/REST — **без SQL и сидинга**.
Помещения нужны как ключ для узлов, камер, показаний и событий; узлы датчиков —
обязательны: без узла в справочнике `ingest-sensors` отбрасывает его показания.
Все эндпойнты требуют `X-API-Key`.

```
GET  /api/v1/rooms                  # список помещений
POST /api/v1/rooms                  # завести помещение или 409 ROOM_ALREADY_EXISTS
GET  /api/v1/sensor-nodes           # список узлов датчиков
POST /api/v1/sensor-nodes           # завести узел: 404 ROOM_NOT_FOUND / 409 NODE_ALREADY_EXISTS
```

**Тело `POST /rooms`** (`id` — человекочитаемый ключ помещения):
```json
{ "id": "room-01", "name": "Кухня", "is_cold": false }
```

**Тело `POST /sensor-nodes`** (`room_id` — id существующего помещения):
```json
{ "id": "node-01", "room_id": "room-01", "placement": "внутри (I2C)", "power": "mains", "note": null }
```

### 3.5 Настройка видеоаналитики: камеры и ROI-зоны

Интерфейс настройки контура под объект: включение камеры и её функций аналитики,
управление ROI-зонами для расчёта % покрытия. Все эндпойнты требуют `X-API-Key`.

```
GET   /api/v1/cameras                         # список камер
POST  /api/v1/cameras                         # завести камеру в справочнике
GET   /api/v1/cameras/{camera_id}             # камера или 404 CAMERA_NOT_FOUND
PATCH /api/v1/cameras/{camera_id}             # enabled и/или тумблеры analytics
DELETE /api/v1/cameras/{camera_id}            # мягко удалить камеру или 404 CAMERA_NOT_FOUND
GET   /api/v1/cameras/{camera_id}/snapshot    # JPEG-кадр от go2rtc (фон для ROI)
GET   /api/v1/cameras/{camera_id}/stream.mjpeg # живой MJPEG-видеопоток (прокси go2rtc)
GET   /api/v1/cameras/{camera_id}/zones       # ROI-зоны камеры
POST  /api/v1/cameras/{camera_id}/zones       # создать ROI-зону
PATCH /api/v1/zones/{zone_id}                 # изменить зону или 404 ZONE_NOT_FOUND
DELETE /api/v1/zones/{zone_id}                # удалить зону или 404 ZONE_NOT_FOUND
```

`GET /cameras/{id}/snapshot` отдаёт `image/jpeg` (не конверт): api-gateway
проксирует кадр у go2rtc по имени потока = `cameras.name`. Используется веб-GUI.

`GET /cameras/{id}/stream.mjpeg` отдаёт живой MJPEG-видеопоток
(`multipart/x-mixed-replace`, не конверт): api-gateway ретранслирует поток go2rtc.
Медиа-эндпойнты (`snapshot`, `stream.mjpeg`) принимают ключ из заголовка
`X-API-Key` **или** query-параметра `?api_key=` — тег `<img>` в браузере не шлёт
заголовки. Ключ в URL — компромисс для внутреннего GUI; наружу не публикуется.

**Веб-GUI настройки** видеоаналитики отдаётся api-gateway по адресу **`/ui/`**
(статический SPA): список камер, тумблеры функций, разметка ROI-зон мышью поверх
кадра-превью. Сам GUI без ключа, его запросы к API несут `X-API-Key`.

**Тело `POST /cameras`** (заводит камеру; альтернатива сид-конфигу `db/seeds/object.yaml`):
```json
{ "room": "room-01", "name": "cam-01", "rtsp_url": "rtsp://camera.local/stream", "enabled": true }
```
`name` обязано совпадать с именем потока в `media-gateway/go2rtc.yaml` (по нему
берётся кадр-превью). `room` — id существующего помещения. Ответ `data` — созданная
камера (с выданным `id`); `analytics=null` (все функции включены).

**Тело `PATCH /cameras/{id}`** (поля необязательны; `analytics` сливается с текущим):
```json
{ "enabled": true, "analytics": { "pose": true, "actions": true, "uniform": true, "coverage": false } }
```
Функции аналитики: `pose`, `actions`, `uniform`, `coverage`. Отсутствие ключа или
`analytics=null` = функция включена. `enabled=false` отключает всю аналитику камеры.

**`DELETE /cameras/{id}` — мягкое удаление.** Камера и её ROI-зоны исчезают из
справочника и обзора, камера перестаёт опрашиваться планировщиком. **История
анализа, стоп-кадры и события по камере сохраняются** (доказательная база ППК) —
строка помечается `deleted_at` и `enabled=false`, физически не удаляется.
Восстановление через интерфейс не предусмотрено. Ответ `data`:
`{ "deleted": "<uuid>" }`; повторное удаление → 404 `CAMERA_NOT_FOUND`. Для
временного отключения камеры (с сохранением в списке) используйте
`PATCH {enabled:false}`.

**Тело `POST /cameras/{id}/zones`** (полигон — ≥3 вершин, координаты нормированы [0..1]):
```json
{ "zone_type": "table", "polygon": [[0.1,0.1],[0.5,0.1],[0.5,0.5]], "note": "стол" }
```
`zone_type`: `table` | `floor` | `window`. Типы зон и модель — `docs/04_DATA_MODEL.md`.

---

### 3.6 Пороги датчиков и расписания (настройка через интерфейс)

Эти справочники настраиваются оператором через веб-GUI (или REST) — без SQL.
Сервисы перечитывают их сами: `ingest-sensors` — пороги каждую минуту, `scheduler`
— расписания каждый тик. Все эндпойнты требуют `X-API-Key`.

```
GET    /api/v1/thresholds                  # список порогов
POST   /api/v1/thresholds                  # создать порог
PATCH  /api/v1/thresholds/{id}             # изменить или 404 THRESHOLD_NOT_FOUND
DELETE /api/v1/thresholds/{id}             # удалить или 404 THRESHOLD_NOT_FOUND
GET    /api/v1/schedules                    # список расписаний (таймер)
POST   /api/v1/schedules                   # создать или 409 SCHEDULE_DUPLICATE_NAME
PATCH  /api/v1/schedules/{id}              # изменить или 404/409 (имя занято)
DELETE /api/v1/schedules/{id}              # удалить или 404 SCHEDULE_NOT_FOUND
```

**Тело `POST /thresholds`** (`room=null` — глобальный порог для всех помещений):
```json
{ "room": "room-02", "metric": "air_temp", "op": ">", "value": 8.0,
  "severity": "warning", "silent_min": 10, "enabled": true }
```
`metric`: `air_temp`|`humidity`|`surface_ir`; `op`: `>`|`<`|`>=`|`<=`;
`severity`: `info`|`warning`|`critical`.

**Тело `POST /schedules`** (периодический запуск видеоанализа — «таймер»):
```json
{ "name": "кухня-15м", "source_type": "stream", "source_ref": "rtsp://camera/stream",
  "room": "room-01", "camera_id": "…", "pipeline": "pose_v1",
  "params": { "fps": 5 }, "interval_min": 15, "enabled": true }
```
Расписания из БД имеют приоритет над легаси-файлом `config/schedules.json` (файл
остаётся поддержанным для совместимости; записи файла берутся, если имя не занято
записью из БД; имя расписания уникально). Коды ошибок: `THRESHOLD_NOT_FOUND`,
`SCHEDULE_NOT_FOUND` (404), `SCHEDULE_DUPLICATE_NAME` (409 — имя занято).

### 3.7 Правила санитарного контроля уборки (#265)

Зона (помещение + тип) должна убираться не реже `interval_hours`; покрытие
последней уборки — не ниже `min_coverage_pct`. Нарушение — событие
`cleaning_overdue` от планировщика (раз на эпизод). Правила перечитываются
планировщиком на каждом тике.

```
GET    /api/v1/cleaning-rules              # список правил
POST   /api/v1/cleaning-rules              # создать или 409 CLEANING_RULE_DUPLICATE
PATCH  /api/v1/cleaning-rules/{id}         # изменить или 404 CLEANING_RULE_NOT_FOUND
DELETE /api/v1/cleaning-rules/{id}         # удалить или 404 CLEANING_RULE_NOT_FOUND
```

**Тело `POST /cleaning-rules`**:
```json
{ "room": "room-01", "zone_type": "table", "interval_hours": 4,
  "min_coverage_pct": 60, "zone_name": "стол у плиты", "enabled": true }
```
`zone_type`: `table`|`floor`|`window` (как у ROI-зон). На пару (room, zone_type)
— одно правило (уникальность). `min_coverage_pct: 0` — покрытие не проверяется.
Несуществующее помещение → 404 `ROOM_NOT_FOUND`.

### 3.7a Правила контроля присутствия (#300, #312)

В помещении в окне времени (например, смена 08:00–17:00) присутствие в рабочей
зоне должно фиксироваться не реже, чем раз в `max_absence_min` минут (события
`presence_detected`, #302). Нарушение — событие `presence_missing` от
планировщика (раз на эпизод). Времена окна — в поясе `PRESENCE_TZ` планировщика
(IANA, по умолчанию UTC); окно дневное (`window_start < window_end`).

```
GET    /api/v1/presence-rules              # список правил
POST   /api/v1/presence-rules              # создать или 409 PRESENCE_RULE_DUPLICATE
PATCH  /api/v1/presence-rules/{id}         # изменить или 404 PRESENCE_RULE_NOT_FOUND
DELETE /api/v1/presence-rules/{id}         # удалить или 404 PRESENCE_RULE_NOT_FOUND
```

**Тело `POST /presence-rules`**:
```json
{ "room": "room-01", "window_start": "08:00", "window_end": "17:00",
  "max_absence_min": 30, "enabled": true }
```
На тройку (room, window_start, window_end) — одно правило (уникальность); на
помещение допускается несколько окон (смены). `PATCH` меняет только
`max_absence_min`/`enabled` (окно — ключ правила: пересоздайте). Несуществующее
помещение → 404 `ROOM_NOT_FOUND`; `window_start >= window_end` → 422.

### 3.8 Сменный/суточный отчёт (санинспекция/ППК, #266)

```
GET /api/v1/reports/sanitation?from=&to=&format=json|csv
```

Отчёт за период (`to` по умолчанию — сейчас): **уборки** (из `coverage_report`:
время, помещение, зона, %), **просрочки** (`cleaning_overdue`) и **холодовая
цепь** — по каждому холодильному помещению (`rooms.is_cold`) мин/макс/среднее
температуры воздуха и **суммарное время вне нормы, мин** (по парам
`threshold_exceeded` → `back_to_normal`; незакрытое превышение считается до
конца периода; превышение, начавшееся до периода, в v1 не видно). `format=csv`
отдаёт файл-вложение `text/csv` (разделитель `;`). `from >= to` → 422.

### 3.9 Обзор объекта для дежурного (#288)

```
GET /api/v1/overview
```

Один агрегат для обзорного экрана (#269): браузеру не нужно делать 5 запросов.
`data`:
```json
{
  "now": "2026-06-10T12:00:00Z",
  "rooms": [ { "id": "room-01", "name": "Цех", "is_cold": false,
               "metrics": { "air_temp": {"value": 5.0, "unit": "C", "ts": "…"},
                            "humidity": {"value": 55.0, "unit": "%", "ts": "…"} } } ],
  "nodes": [ { "id": "node-01", "room_id": "room-01", "online": true, "last_ts": "…" } ],
  "cameras": [ { "id": "…", "name": "Кухня-1", "room_id": "room-01",
                 "enabled": true, "online": false } ],
  "recent_events": [ /* последние события журнала, новые сверху */ ],
  "active_alerts": 2
}
```

Живость узлов (`online`) — из свежести последнего показания (нет отдельного
события «узел вернулся»); порог по умолчанию 10 мин. Живость камер — из последних
событий `camera_offline`/`camera_online` (#283); камера без таких событий
считается на связи. `active_alerts` — число неподтверждённых событий важности
≥ `warning` (#264). События берутся из журнала (log-service).

---

### 3.10 Аудит значимых действий (#292)

```
GET /api/v1/audit?from=&to=&limit=   # только роль admin
```

Каждое изменяющее действие настройки (POST/PATCH/DELETE справочников, камер,
ROI-зон, порогов, расписаний, правил уборки) и подтверждение события
(`POST /events/{id}/ack`) записываются в `audit_log`: кто (`actor`/`role` —
в v1 это роль исполнителя, имени пользователя при ключах в `.env` нет), что
(`action` — HTTP-метод), над чем (`target` — путь), когда (`ts`). Запрещённые
попытки (403) не пишутся (проверка роли срабатывает раньше). `data`:
```json
{ "items": [ { "id": 12, "ts": "2026-06-10T12:00:00+00:00", "actor": "admin",
               "role": "admin", "action": "PATCH",
               "target": "/api/v1/cameras/…", "detail": null } ], "total": 1 }
```

---

## 4. Разъёмы для АУРА (`/integration/*`) — заглушены в v1

Эти эндпойнты **существуют** в v1, но возвращают `501 NOT_IMPLEMENTED`, пока
`aura_integration_enabled=false`. Код помечен `# СТЫК-АУРА (v2)`. Метка issue —
`stub-aura`.

### 4.1 АУРА ставит задание на анализ файла (v2)
```
POST /api/v1/integration/analysis-tasks
X-API-Key: <ключ>
```
Тело (v2):
```json
{
  "source_type": "file",
  "source_ref": "/data/artifacts/2026-06-05/clip-0007.mp4",  // файл на общем томе
  "room": "room-03",
  "pipeline": "pose_v1",
  "callback_url": "http://aura/notify"   // опц., webhook о готовности
}
```
**v1-поведение:** `501`, тело-конверт с `error.code = "NOT_IMPLEMENTED"`.

### 4.2 АУРА читает события (v2)
```
GET /api/v1/integration/events?from=&to=&type=
```
**v1-поведение:** `501`.

### 4.3 АУРА передаёт настройки (v2)
```
PUT /api/v1/integration/settings
```
Тело (v2): пороги, расписания, какие pipeline включены и т.п.
**v1-поведение:** `501`.

### 4.4 Уведомление о готовности задания (v2, мы → АУРА)
В v2, если у задания задан `callback_url`, `api-gateway` шлёт АУРА POST:
```json
{ "task_id": "uuid", "status": "done", "events": ["uuid", "..."],
  "artifacts": ["/data/artifacts/2026-06-05/clip-0007_kp.json"] }
```
В v1 механизм не активируется.

---

## 5. Версионирование и совместимость

- Префикс `/api/v1` фиксируем. Несовместимые изменения — новый префикс `/api/v2`.
- Добавление полей в JSON — совместимо; удаление/переименование — нет, требует
  версии и обновления этого документа.
- Включение интеграции с АУРА — через фичефлаг `aura_integration_enabled`, **без**
  изменения путей. Пути `/integration/*` стабильны с v1.

---

## 6. Что из этого — задачи Кода

- `shared/`: модель конверта (`Envelope`), коды ошибок, базовые Pydantic-схемы
  событий/заданий/показаний.
- `api-gateway`: эндпойнты §3 (рабочие) и §4 (заглушки `501` за фичефлагом).
- Контрактные тесты: успех/ошибка-конверт; `/integration/*` отдаёт `501` при
  выключенном флаге.
- Поддерживать соответствие OpenAPI ↔ этот документ.
