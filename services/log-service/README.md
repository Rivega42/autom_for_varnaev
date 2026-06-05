# log-service

Единый журнал событий: принимает события от `ingest-sensors` и `video-analytics`
(внутренний REST), пишет в таблицу `events`, отдаёт `GET /events`. Эпик E3.

- Python-пакет: `log_service` (уникальное имя).
- Контракт — `docs/03_API_CONTRACT.md`; схема события — `docs/04_DATA_MODEL.md` §4.
