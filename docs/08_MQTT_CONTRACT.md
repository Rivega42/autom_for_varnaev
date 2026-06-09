# 08 · Контракт MQTT (топики и payload датчиков)

Узлы датчиков (ESP32-C3, ESPHome) **сами публикуют** показания в брокер
`mqtt-broker` (Mosquitto). Сервер их не опрашивает. Здесь зафиксирован формат
топиков и сообщений, по которому `ingest-sensors` разбирает показания в модель
`Reading` (см. `docs/04_DATA_MODEL.md` §3 и `shared/monitoring_shared`).

---

## 1. Топики

Базовый префикс задаётся переменной `MQTT_TOPIC_PREFIX` (по умолчанию `monitoring`).

| Назначение | Топик | Направление |
|---|---|---|
| Показание метрики | `<prefix>/<node_id>/<metric>` | узел → брокер → ingest |
| Доступность узла (LWT) | `<prefix>/<node_id>/status` | узел → брокер |

- `<node_id>` — идентификатор узла из справочника `sensor_nodes` (напр. `node-01`).
- `<metric>` — одна из метрик v1: `air_temp` | `humidity` | `surface_ir` | `uv_index` | `uv_c`.
- `room_id` в payload **не передаётся**: помещение определяется по связи
  `sensor_nodes.room_id` на стороне `ingest-sensors`.

---

## 2. Payload показания (JSON, UTF-8)

```json
{ "value": 8.7, "unit": "C", "ts": "2026-06-05T10:30:00Z" }
```

| Поле | Тип | Обяз. | Смысл |
|---|---|---|---|
| `value` | number | да | значение метрики |
| `unit` | string | да | единица: `C` (°C) или `%` |
| `ts` | string (ISO-8601 UTC) | нет | момент измерения; если нет — берётся время приёма сервером |

`ingest-sensors` собирает из топика и payload модель `Reading`
(`ts`, `node_id`, `room_id`, `metric`, `value`, `unit`).

---

## 3. Примеры

```
monitoring/node-01/air_temp     {"value": 23.4, "unit": "C"}
monitoring/node-01/humidity     {"value": 41.0, "unit": "%"}
monitoring/node-01/surface_ir   {"value": 4.2,  "unit": "C", "ts": "2026-06-05T10:30:00Z"}
monitoring/node-01/uv_index     {"value": 1.2,  "unit": "index"}
monitoring/node-01/uv_c         {"value": 2.5,  "unit": "mW/cm2"}
monitoring/node-02/status       online
```

- `surface_ir` — бесконтактная ИК-температура поверхности (MLX90614).
- `uv_index` — общий УФ-индекс / УФ-A (LTR390, I²C), безразмерный.
- `uv_c` — бактерицидный УФ-C 254 нм (GUVC-S10GD, аналоговый), мВт/см² — контроль
  работы кварцевых ламп (ППК).
- `status` (LWT) — `online` при подключении, `offline` (retained, Last Will) при
  обрыве; полезно как дополнительный сигнал к контролю «тишины» узла
  (`sensor_silent`), но основной критерий тишины — отсутствие показаний дольше
  `thresholds.silent_min`.

---

## 4. Обработка некорректных сообщений

`ingest-sensors` при невалидном топике/payload (нераспознанная метрика, битый
JSON, отсутствие `value`/`unit`) **логирует и пропускает** сообщение, не падая.
Это часть задачи парсинга (E2.5).

---

## 5. Соответствие

- Метрики и единицы — `docs/04_DATA_MODEL.md` §3.
- Переменные `MQTT_*` — `.env.example`.
- Эталонные ESPHome-конфиги, публикующие в эти топики, — `firmware/esphome/`
  (E2.11–E2.12).
