# Развёртывание у заказчика — пошагово (закрытая поставка образов)

> Эта инструкция — для **развёртывания контура мониторинга на сервере заказчика**.
> Наши сервисы поставляются **готовыми закрытыми образами** из реестра (их не нужно
> собирать из исходников). Запуск — фактически одной командой `docker compose up`.
>
> Инструкция написана **максимально подробно**. Если ты раньше не работал с Docker —
> просто выполняй шаги по порядку, копируя команды. Команды даны для **Linux**
> (рекомендуемый сервер) и для **Windows (PowerShell)**.
>
> Связанные документы: общая [`10_DEPLOYMENT.md`](10_DEPLOYMENT.md) (сборка из
> исходников, для разработчиков), [`14_LICENSING.md`](14_LICENSING.md) (лицензия),
> [`15_SENSOR_QUICKSTART.md`](15_SENSOR_QUICKSTART.md) (прошивка датчиков),
> [`02_NETWORK.md`](02_NETWORK.md) (сеть/порты).

---

## 0. Коротко (TL;DR) — если уже всё знаешь

```bash
# 1. получить комплект и войти в каталог
git clone https://github.com/Rivega42/autom_for_varnaev.git && cd autom_for_varnaev
# 2. (если образы приватные) залогиниться в реестр
echo "<ТОКЕН>" | docker login ghcr.io -u <ЛОГИН> --password-stdin
# 3. подготовить .env (заполнить пароли, API_KEY, LICENSE_KEY)
cp .env.example .env && nano .env
# 4. камеры
cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml && nano media-gateway/go2rtc.yaml
# 5. модель видеоаналитики
bash scripts/fetch_model.sh
# 6. запустить
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
# 7. проверить
docker compose -f docker-compose.release.yml ps
```

Дальше — то же самое, но подробно и с пояснениями.

---

## 1. Что понадобится (требования)

**Железо/ОС сервера:**
- Linux (Ubuntu/Debian — лучший вариант для прод) **или** Windows 10/11 / Windows Server.
- Минимум **4 ГБ ОЗУ** (рекомендуется 8 ГБ, видеоаналитика на CPU прожорлива), **20+ ГБ** свободного диска.
- **Доступ в интернет** с сервера (нужен, чтобы скачать образы и модель).

**Софт (установить заранее):**
- **Docker Engine** + плагин **Docker Compose v2**.
  - Linux: установка по официальной инструкции docker.com (пакет `docker-ce` + `docker-compose-plugin`).
  - Windows: **Docker Desktop**.
- Проверь, что всё стоит:
  ```bash
  docker --version            # ожидается Docker version 24+ (у нас тест на 27)
  docker compose version      # ожидается Docker Compose version v2.x
  ```
  Если `docker compose version` ругается «unknown command» — у тебя старый Compose v1
  (`docker-compose` через дефис). Нужен **v2** (через пробел). Обнови Docker.

**От нас (поставщика) ты должен получить:**
1. **Комплект файлов** — этот репозиторий (через `git clone` или ZIP-архив). В нём
   лежат `docker-compose.release.yml`, конфиги объекта (init БД, дашборды, примеры)
   и инструкции. Сами исходники сервисов в запуске **не используются** — тянутся образы.
2. **Лицензионный ключ** (строка) — снимает демо-ограничение (см. §4).
3. **Доступ к образам в реестре** — если образы приватные, мы дадим **логин и токен**
   (Personal Access Token с правом `read:packages`). Если образы публичные — доступ не нужен.

---

## 2. Получить комплект и войти в каталог

**Вариант А — git (если установлен git):**
```bash
git clone https://github.com/Rivega42/autom_for_varnaev.git
cd autom_for_varnaev
```

**Вариант Б — ZIP-архив:** распакуй полученный архив и зайди в распакованную папку.
В Windows (PowerShell):
```powershell
Expand-Archive .\autom_for_varnaev.zip -DestinationPath .
Set-Location .\autom_for_varnaev
```

> Все команды ниже выполняются **из корня этого каталога** (там, где лежит файл
> `docker-compose.release.yml`). Проверь: `ls docker-compose.release.yml` (Linux)
> или `dir docker-compose.release.yml` (Windows) — файл должен находиться.

---

## 3. Получить образы наших сервисов — два варианта

**Вариант A (офлайн, по умолчанию для этой поставки): образы из архива.**
Если в комплекте есть файл `images.tar` — реестр и интернет для образов **не нужны**.
Загрузи образы в Docker одной командой:
```bash
docker load -i images.tar           # Linux/Mac/Git Bash
```
```powershell
docker load -i images.tar           # Windows
# либо запусти готовый скрипт из комплекта:  ./install.ps1
```
Это займёт несколько минут (образы большие). После загрузки переходи к §4.
Команды `pull` в §8 при офлайн-поставке **пропускай** — образы уже в Docker.

**Вариант B (из реестра ghcr.io):** если `images.tar` нет, образы тянутся из реестра.
- Публичные образы — ничего не нужно, Docker скачает сам (§8 `pull`).
- Приватные — один раз залогинься (мы пришлём логин и токен):
  ```bash
  echo "<ТОКЕН>" | docker login ghcr.io -u <ЛОГИН> --password-stdin
  ```
  ```powershell
  "<ТОКЕН>" | docker login ghcr.io -u <ЛОГИН> --password-stdin
  ```
  Ответ `Login Succeeded`.

---

## 4. Заполнить `.env` (пароли, ключ API, лицензия)

`.env` — файл с настройками и паролями. Его **нет** в комплекте (секреты не
поставляются), но есть подробный образец `.env.example`.

1. Скопируй образец в рабочий файл:
   - Linux: `cp .env.example .env`
   - Windows: `Copy-Item .env.example .env`
2. Открой `.env` в редакторе (`nano .env` / блокнот) и **обязательно** задай:

   | Переменная | Что это | Пример значения |
   |---|---|---|
   | `POSTGRES_PASSWORD` | пароль основной БД | придумай длинный, напр. `Xk9$pLm2...` |
   | `POSTGRES_RO_PASSWORD` | пароль read-only пользователя БД (для Grafana) | другой длинный пароль |
   | `API_KEY` | ключ доступа к REST/GUI (заголовок `X-API-Key`), роль admin | длинная случайная строка |
   | `GF_SECURITY_ADMIN_PASSWORD` | пароль входа в Grafana (логин `admin`) | длинный пароль |
   | `LICENSE_KEY` | **лицензионный ключ от нас** | строка, что мы прислали |

   > **Без `LICENSE_KEY`** контур запустится в **демо-режиме**: только **1 помещение,
   > 1 камера, 1 узел датчиков**. Вставь присланный ключ, чтобы снять ограничение
   > (подробнее — [`14_LICENSING.md`](14_LICENSING.md)).

3. `REGISTRY` и `IMAGE_TAG` в `.env` **оставь как есть** (`ghcr.io/rivega42` и версия,
   которую мы назвали). Меняй только если мы прямо сказали другую версию.

4. **Совет «чтобы не печатать `-f` каждый раз».** Добавь в `.env` строку:
   ```
   COMPOSE_FILE=docker-compose.release.yml
   ```
   Тогда любая команда `docker compose ...` будет автоматически работать с релизным
   файлом, и `-f docker-compose.release.yml` можно не писать. (В командах ниже мы
   всё равно пишем `-f` явно — так сработает в любом случае.)

> Как придумать длинный пароль/ключ: Linux — `openssl rand -hex 24`; Windows —
> `-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 32 | %{[char]$_})`.

---

## 5. Настроить камеры (`go2rtc.yaml`)

Список камер (RTSP-адреса с логином/паролем) хранится отдельно и в комплект не входит
— только образец.

1. Скопируй образец:
   - Linux: `cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml`
   - Windows: `Copy-Item media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml`
2. Открой `media-gateway/go2rtc.yaml` и впиши свои камеры. Пример блока:
   ```yaml
   streams:
     cam-kitchen: rtsp://login:password@192.168.1.50:554/Streaming/Channels/101
     cam-pack:    rtsp://login:password@192.168.1.51:554/Streaming/Channels/101
   ```
   Имя потока (`cam-kitchen`) дальше указывается при заведении камеры в системе (§10).

> Если камер пока нет — можно оставить пустой список `streams: {}` и добавить позже,
> система поднимется и без камер (видеоаналитика просто не будет получать кадры).

---

## 6. Положить модель видеоаналитики

Видеоаналитике нужен бинарный файл модели `models/pose_landmarker.task` (~10–30 МБ).
Без него сервис `video-analytics` **не стартует** (это by design).

- **Linux:**
  ```bash
  bash scripts/fetch_model.sh
  ```
- **Windows:** запусти тот же скрипт в Git Bash, **или** скачай файл вручную по
  ссылке из [`models/README.md`](../models/README.md) и положи как
  `models/pose_landmarker.task`.

Проверь, что файл на месте:
- Linux: `ls -lh models/pose_landmarker.task`
- Windows: `dir models\pose_landmarker.task`

---

## 7. (Опционально) расписания видеоанализа

Если нужно, чтобы аналитика запускалась **по таймеру**, создай файл расписаний:
- Linux: `cp config/schedules.example.json config/schedules.json`
- Windows: `Copy-Item config/schedules.example.json config/schedules.json`

Без этого файла периодических заданий не будет (можно настроить позже; разовый анализ
запускается из GUI). Формат — см. [`config/README.md`](../config/README.md).

---

## 8. Запуск

1. Скачать образы (один раз, может занять несколько минут — образы большие):
   ```bash
   docker compose -f docker-compose.release.yml pull
   ```
2. Поднять весь стек в фоне:
   ```bash
   docker compose -f docker-compose.release.yml up -d
   ```

   > **Хочешь сразу увидеть populated-дашборды «как у вендора»** (на синтетических
   > данных, без реального железа)? Подними с демо-оверлеем:
   > ```bash
   > docker compose -f docker-compose.release.yml -f docker-compose.demo.release.yml up -d
   > ```
   > Демо-генератор начнёт слать показания, появятся графики и события. Когда
   > подключишь реальные датчики/камеры — переходи на «боевой» запуск без оверлея.

**Что произойдёт по шагам (это нормально):**
1. поднимется БД `db`, дождётся готовности (healthcheck);
2. одноразовый сервис `migrate` применит схему БД и **завершится с кодом 0**
   (он и должен «выйти» — это не ошибка);
3. поднимутся `log-service`, `api-gateway`, `ingest-sensors`, `scheduler`,
   `video-analytics`, `grafana`, `mqtt-broker`, `media-gateway`, `backup`.

Первый старт занимает 1–3 минуты (БД инициализируется, сервисы ждут друг друга).

---

## 9. Проверка, что всё поднялось

1. Статус контейнеров:
   ```bash
   docker compose -f docker-compose.release.yml ps
   ```
   Ожидается: сервисы в состоянии `running`/`healthy`; `migrate` — `exited (0)`.

2. Если `migrate` не отработал — посмотри его лог:
   ```bash
   docker compose -f docker-compose.release.yml logs migrate
   ```
   Должна быть строка вида `running upgrade ... -> 00NN ...` и завершение без ошибок.

3. Smoke-проверка (подставь свой `API_KEY` из `.env`):
   ```bash
   # REST жив (ответ в конверте), нужен ключ:
   curl -H "X-API-Key: ВАШ_API_KEY" http://localhost:8000/api/v1/health

   # Разъёмы АУРА в v1 заглушены — это ожидаемый ответ 501:
   curl -i -H "X-API-Key: ВАШ_API_KEY" http://localhost:8000/api/v1/integration/events
   ```
4. Открой в браузере (если ставишь на сервере без графики — с другого ПК по IP сервера):
   - **GUI настройки** (камеры, тумблеры аналитики, разметка зон): `http://<сервер>:8000/ui/`
     — введи `API_KEY` в шапке, нажми «Загрузить камеры».
   - **Экран дежурного** (помещения, узлы, лента событий): `http://<сервер>:8000/ui/overview.html`
   - **Grafana** (графики и журнал): `http://<сервер>:3000` — логин `admin`,
     пароль = `GF_SECURITY_ADMIN_PASSWORD` из `.env`.

---

## 10. Завести объект (помещения, узлы датчиков, камеры)

Система стартует с пустыми справочниками. Заполнить — два способа:

**Способ А (рекомендуется для начала): через GUI/REST.** В GUI `http://<сервер>:8000/ui/`
заводятся камеры; помещения и узлы датчиков — через REST (`POST /api/v1/rooms`,
`/api/v1/sensor-nodes`, `/api/v1/cameras`, см. [`03_API_CONTRACT.md`](03_API_CONTRACT.md)).

**Способ Б (массово из файла):** заполни `db/seeds/object.yaml` по образцу
`db/seeds/object.example.yaml` и примени:
```bash
# проверка (ничего не пишет в БД):
docker compose -f docker-compose.release.yml --profile seed run --rm seed
# запись в БД:
docker compose -f docker-compose.release.yml --profile seed run --rm seed --apply
```

> Важно: **каждый узел датчиков** (и его `node_id`) должен быть заведён **до** того,
> как датчик начнёт слать данные — иначе показания молча отбрасываются.

---

## 11. Прошивка датчиков

ESPHome Dashboard можно поднять прямо здесь (по требованию):
```bash
docker compose -f docker-compose.release.yml --profile tools up -d esphome
# откроется на http://<сервер>:6052
```
Пошагово (сборка узла, secrets, node_id, прошивка по USB/OTA) — в
[`15_SENSOR_QUICKSTART.md`](15_SENSOR_QUICKSTART.md). Каталог готовых покупных
датчиков (WiFi/Zigbee) — в [`16_READYMADE_SENSORS.md`](16_READYMADE_SENSORS.md).

---

## 12. Эксплуатация

| Действие | Команда |
|---|---|
| Посмотреть статус | `docker compose -f docker-compose.release.yml ps` |
| Логи всех сервисов | `docker compose -f docker-compose.release.yml logs -f` |
| Логи одного сервиса | `docker compose -f docker-compose.release.yml logs -f api-gateway` |
| Остановить (данные сохранятся) | `docker compose -f docker-compose.release.yml down` |
| Запустить снова | `docker compose -f docker-compose.release.yml up -d` |
| Перезапустить сервис | `docker compose -f docker-compose.release.yml restart video-analytics` |

**Бэкапы БД** делает сервис `backup` автоматически (по умолчанию раз в сутки, хранит
14 последних) в docker-том `backups`. Восстановление и периодичность — см.
[`09_OPERATIONS.md`](09_OPERATIONS.md) (если есть) / `BACKUP_*` в `.env`.

**Обновление версии** (когда мы пришлём новый `IMAGE_TAG`):
```bash
# 1. поправь IMAGE_TAG в .env на новую версию
docker compose -f docker-compose.release.yml pull           # скачать новые образы
docker compose -f docker-compose.release.yml run --rm migrate   # применить новые миграции БД
docker compose -f docker-compose.release.yml up -d          # перезапустить на новой версии
```

---

## 13. Что открыто наружу и безопасность

Наружу (на хост/LAN) публикуются **только три порта**:
- **8000** — REST API + веб-GUI (защищён `API_KEY`);
- **3000** — Grafana (логин/пароль);
- **1883** — MQTT-брокер (для приёма данных от датчиков в локальной сети объекта).

Всё остальное (БД, лог-сервис, видеоаналитика, медиа-шлюз) живёт во **внутренней
сети Docker** и наружу недоступно.

Рекомендации:
- **Не выставляй порты 8000/3000 напрямую в интернет** без необходимости. Если нужен
  внешний доступ — только через защищённый канал (VPN/обратный прокси с TLS).
- `API_KEY` обязателен и не должен быть пустым (иначе REST открыт без ключа).
- Разъёмы интеграции с АУРА в этой поставке **выключены** (`AURA_INTEGRATION_ENABLED=false`),
  отвечают `501`. Включаются позже флагом, без переустановки.

---

## 14. Если что-то не так (траблшутинг)

| Симптом | Причина и решение |
|---|---|
| `... POSTGRES_PASSWORD должен быть задан в .env` при запуске | Не заполнен `.env`. Вернись к §4, задай пароли. |
| `docker compose` пишет `unknown shorthand flag` / не понимает команду | Старый Compose v1. Нужен **v2** (`docker compose`, через пробел). Обнови Docker. |
| Образ не качается: `denied` / `unauthorized` / `manifest unknown` | Образы приватные — выполни `docker login ghcr.io` (§3); проверь, что `REGISTRY`/`IMAGE_TAG` в `.env` совпадают с тем, что мы прислали. |
| `video-analytics` постоянно перезапускается, в логах «модель не найдена» | Нет файла модели. Выполни §6, проверь `models/pose_landmarker.task`. |
| Порт занят: `address already in use` (8000/3000/1883) | На сервере уже что-то слушает порт. Освободи порт или поменяй левую часть проброса в `docker-compose.release.yml` (напр. `"18000:8000"`). |
| В системе можно завести только 1 помещение/камеру/узел | Демо-режим: не задан/неверен `LICENSE_KEY`. Вставь ключ в `.env`, перезапусти `api-gateway`. |
| `migrate` завершился с ошибкой | Посмотри `logs migrate`. Чаще — неверный пароль БД в `.env` или не успела подняться `db` (перезапусти `up -d`). |
| Камеры не отображаются / нет кадра | Проверь `media-gateway/go2rtc.yaml` (RTSP-адрес, логин/пароль, сетевую доступность камеры с сервера). |
| Не приходят данные с датчика | Узел не заведён в справочнике (§10), либо неверный `node_id`/топик. Формат — [`08_MQTT_CONTRACT.md`](08_MQTT_CONTRACT.md). |
| Кадры-улики не сохраняются; в логах `PermissionError` на `/data/artifacts` | Том артефактов не выровнен по правам. Это делает one-shot `artifacts-init` (образ `busybox`, выставляет владельца `10001:10001`) перед стартом сервисов. Проверь `logs artifacts-init`; если образа нет в офлайн-комплекте — он должен быть в `images.tar`. Перезапусти `up -d`. |

Если не помогло — пришли нам вывод:
```bash
docker compose -f docker-compose.release.yml ps
docker compose -f docker-compose.release.yml logs --tail=100
```

---

## Приложение (для нас, поставщика): как опубликовать образы

> Этот раздел — **не для заказчика**, а для нас. Заказчику образы уже опубликованы.

Образы собираются и публикуются скриптом из корня репозитория. Нужен Docker и
**Personal Access Token** GitHub со scope **`write:packages`** (обычного `gh`-токена
недостаточно — у него нет этого права; создай classic PAT в настройках GitHub или
`gh auth refresh -h github.com -s write:packages`).

```bash
# Linux/Git Bash:
REGISTRY=ghcr.io/rivega42 IMAGE_TAG=v1.0.0 GHCR_TOKEN=<PAT> \
  ./scripts/publish_release_images.sh
```
```powershell
# Windows PowerShell:
$env:REGISTRY="ghcr.io/rivega42"; $env:IMAGE_TAG="v1.0.0"; $env:GHCR_TOKEN="<PAT>"
./scripts/publish_release_images.ps1
```

Скрипт собирает 8 образов (`api-gateway` и `video-analytics` — закрытые, через
Nuitka/distroless) и публикует их в реестр. После первой публикации **сделай пакеты
ghcr публичными** (Packages → Package settings → Change visibility → Public), чтобы
заказчик тянул их без логина; либо выдай ему токен с `read:packages`.
