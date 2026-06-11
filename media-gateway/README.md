# media-gateway

Медиа-шлюз камер (go2rtc): приём RTSP/ONVIF, релей потока воркеру `video-analytics`
и превью в браузер (WebRTC), снятие CORS-проблемы дешёвых камер. Эпик E4.
См. `docs/01_ARCHITECTURE.md` §4.2.

- `go2rtc.yaml.example` — пример конфига потоков (в репозитории).
- `go2rtc.yaml` — реальный конфиг объекта; создаётся копированием примера:
  `cp media-gateway/go2rtc.yaml.example media-gateway/go2rtc.yaml`.
  Файл в `.gitignore`: RTSP-URL камер содержат логин/пароль, в репозиторий
  они не попадают (CLAUDE.md §5). `scripts/bootstrap.sh` создаёт его из
  примера автоматически, если файла ещё нет.
- В v1 сервис только во внутренней сети `internal`.
