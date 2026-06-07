# 07 · Взаимодействие компонентов

Как компоненты работают вместе в основных сценариях v1. Диаграммы Mermaid
рендерятся на GitHub. Контракты — [`docs/03_API_CONTRACT.md`](../03_API_CONTRACT.md)
и [`docs/08_MQTT_CONTRACT.md`](../08_MQTT_CONTRACT.md); процессные `.bpmn`-исходники
(жизненный цикл задания, поток события) — в этом же каталоге.

---

## A. Поток датчиков → показания и события

Узлы сами публикуют в MQTT; сервер их не опрашивает. Показания копятся в БД,
наружу контур отдаёт **события** (по порогам и «тишине»), а не сырые ряды.

```mermaid
sequenceDiagram
    autonumber
    participant N as Узел ESP32-C3 (ESPHome)
    participant M as mqtt-broker
    participant I as ingest-sensors
    participant DB as db (TimescaleDB)
    participant L as log-service

    N->>M: publish показание (t°/влажность/ИК)
    M->>I: доставка по подписке
    I->>DB: INSERT sensor_readings
    I->>I: сверка с thresholds / контроль «тишины»
    alt порог превышен / возврат к норме / узел молчит
        I->>L: POST событие (message на русском)
        L->>DB: INSERT events
    end
```

---

## B. Видеоаналитика по расписанию

Планировщик создаёт задание; воркер берёт его из очереди, гоняет кадры через
MediaPipe, шлёт события, сохраняет скриншот-доказательство и проставляет статус.

```mermaid
sequenceDiagram
    autonumber
    participant S as scheduler
    participant DB as db (analysis_tasks)
    participant V as video-analytics
    participant G as media-gateway
    participant L as log-service
    participant A as том artifacts

    S->>DB: INSERT analysis_task (queued, trigger=schedule)
    V->>DB: claim_next_task → running
    V->>DB: load_camera_zones по camera_id
    loop кадры (5–8 fps)
        G-->>V: кадр (RTSP→поток)
        V->>V: поза, действия, «белый халат», heat-маска
    end
    V->>L: события pose/action/condition/coverage
    L->>DB: INSERT events
    opt были события
        V->>A: сохранить скриншот
        V->>DB: INSERT artifacts (screenshot, task_id)
    end
    V->>DB: статус done + result
```

---

## C. Внешний доступ: REST и дашборды

Единственный REST-вход — `api-gateway` (с `X-API-Key`). Grafana читает БД
напрямую под read-only пользователем. Разъёмы АУРА в v1 заглушены.

```mermaid
sequenceDiagram
    autonumber
    participant O as Оператор / клиент
    participant API as api-gateway
    participant L as log-service
    participant DB as db
    participant GR as grafana

    O->>API: GET /api/v1/events (X-API-Key)
    API->>L: проксирование запроса
    L->>DB: SELECT events
    DB-->>O: события (единый конверт)

    O->>API: GET /api/v1/readings · POST /api/v1/analysis-tasks
    API->>DB: SELECT/INSERT
    DB-->>O: данные (конверт)

    O->>API: любой /api/v1/integration/*
    API-->>O: 501 Not Implemented (СТЫК-АУРА v2)

    O->>GR: дашборды :3000
    GR->>DB: SELECT (read-only)
```

---

## D. Старт стека (порядок зависимостей)

`docker compose up` сам выдерживает порядок: БД → миграции → прикладные сервисы.

```mermaid
flowchart LR
    DB["db<br/>healthy"] --> MIG["migrate<br/>alembic upgrade head"]
    MIG -->|"completed_successfully"| SVC
    subgraph SVC["Прикладные сервисы"]
      direction TB
      LOG[log-service]
      API[api-gateway]
      ING[ingest-sensors]
      SCH[scheduler]
      VA[video-analytics]
      GRAF[grafana]
    end
```

> Подробности развёртывания и проверки — [`docs/10_DEPLOYMENT.md`](../10_DEPLOYMENT.md);
> эксплуатация (бэкап, перезапуск, артефакты) — [`docs/09_OPERATIONS.md`](../09_OPERATIONS.md).
