# media-gateway

Медиа-шлюз камер (go2rtc): приём RTSP/ONVIF, релей потока воркеру `video-analytics`
и превью в браузер (WebRTC), снятие CORS-проблемы дешёвых камер. Эпик E4.
См. `docs/01_ARCHITECTURE.md` §4.2.

- `go2rtc.yaml` — конфиг потоков (реальные адреса камер — из справочника `cameras`/секретов).
- В v1 сервис только во внутренней сети `internal`.
