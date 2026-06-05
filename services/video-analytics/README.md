# video-analytics

Видеоаналитика: порт рабочего PoC (`reference/motion-log.html`) на MediaPipe
`PoseLandmarker`. Источник кадров = `stream` (media-gateway) | `file` (том).
На выходе — события в `log-service` и артефакты на томе. Эпик E4.

- Python-пакет: `video_analytics` (уникальное имя).
- Тяжёлые зависимости (`mediapipe`, `opencv`) — runtime сервиса, не в CI:
  детектор поз изолирован за абстракцией `PoseDetector`, логика тестируется
  на синтетических ландмарках.
- Спецификация — `docs/07_VIDEO_ANALYTICS.md`; PoC — `reference/`.
