# 06 · Состав продукта (компоненты)

Из чего состоит контур: контейнеры, сети, тома, что опубликовано наружу.
Источник истины — [`docs/01_ARCHITECTURE.md`](../01_ARCHITECTURE.md) и
[`docker-compose.yml`](../../docker-compose.yml). Диаграмма рендерится на GitHub
(Mermaid); правится прямо в этом файле в одном PR с кодом (эпик E8).

```mermaid
flowchart TB
  subgraph OBJ["Объект (вне Docker)"]
    SENS["Узлы датчиков<br/>ESP32-C3 + SHT4x + MLX90614<br/>(ESPHome)"]
    CAMS["IP-камеры<br/>RTSP / ONVIF"]
    OP["Оператор<br/>(браузер)"]
  end

  subgraph SRV["Физический сервер · Docker Compose"]
    direction TB

    subgraph INT["Сеть internal (наружу не видна)"]
      direction TB
      DB[("db<br/>TimescaleDB · PG16")]
      MIG["migrate<br/>alembic upgrade head<br/>(one-shot)"]
      MQTT["mqtt-broker<br/>Mosquitto"]
      ING["ingest-sensors<br/>воркер MQTT→БД"]
      MG["media-gateway<br/>go2rtc"]
      VA["video-analytics<br/>MediaPipe PoseLandmarker"]
      SCH["scheduler<br/>задания по расписанию"]
      LOG["log-service<br/>единый журнал"]
      API["api-gateway<br/>единственный REST-вход<br/>+ разъёмы АУРА (501)"]
      GRAF["grafana<br/>дашборды"]
    end

    subgraph AURANET["Сеть integration (с АУРА)"]
      AURA["АУРА · контейнеры заказчика<br/>(видеозапись, ППК, тех.карты)<br/>— НЕ наш контур"]
    end

    subgraph VOLS["Тома"]
      VDB[("db_data")]
      VART[("artifacts")]
      VMQ[("mqtt_data")]
      VGF[("grafana_data")]
    end
  end

  %% Снаружи внутрь (опубликованные порты)
  SENS -->|"MQTT :1883"| MQTT
  CAMS -->|"RTSP"| MG
  OP -->|"HTTPS :8000 · X-API-Key"| API
  OP -->|":3000"| GRAF

  %% Поток датчиков
  MQTT --> ING
  ING -->|показания| DB
  ING -->|события| LOG

  %% Видеоаналитика
  SCH -->|создаёт analysis_task| DB
  MG -->|кадры| VA
  VA -->|статус/result| DB
  VA -->|события| LOG
  VA -->|скриншот| VART

  %% Журнал и чтение
  LOG --> DB
  GRAF -->|read-only| DB
  API -->|events| LOG
  API -->|readings/tasks| DB

  %% Миграции до старта сервисов
  MIG --> DB

  %% Тома
  DB --- VDB
  MQTT --- VMQ
  GRAF --- VGF

  %% Мост к АУРА — в v1 обмена нет (заглушки 501)
  API -. "integration (v2)" .- AURA

  classDef ours fill:#e8f0fe,stroke:#3367d6,color:#10204a;
  classDef ext fill:#f1f3f4,stroke:#9aa0a6,color:#202124;
  classDef vol fill:#fef7e0,stroke:#f9ab00,color:#3c2c00;
  class DB,MIG,MQTT,ING,MG,VA,SCH,LOG,API,GRAF ours;
  class SENS,CAMS,OP,AURA ext;
  class VDB,VART,VMQ,VGF vol;
```

## Что опубликовано наружу

| Порт | Контейнер | Назначение |
|---|---|---|
| `8000` | `api-gateway` | единственный внешний REST-вход (защищён `X-API-Key`) |
| `3000` | `grafana` | дашборды оператора |
| `1883` | `mqtt-broker` | приём показаний от узлов датчиков |

Всё остальное (`db`, `migrate`, `log-service`, `ingest-sensors`, `scheduler`,
`video-analytics`, `media-gateway`) живёт только в сети `internal`.

## Граница АУРА (v1)

`api-gateway` подключён к обеим сетям (`internal` + `integration`) как будущий
мост к АУРА, но в v1 разъёмы `/api/v1/integration/*` отвечают `501 Not Implemented`
(фичефлаг `AURA_INTEGRATION_ENABLED=false`). Обмена по сети `integration` нет.
