# models — модели для видеоаналитики

Сюда кладётся бинарная модель MediaPipe Tasks `PoseLandmarker` (пайплайн
`pose_v1`). Каталог монтируется в контейнер `video-analytics` как `/models`
(см. `docker-compose.yml`), путь к файлу задаётся `ANALYTICS_MODEL_PATH`
(по умолчанию `/models/pose_landmarker.task`).

Модель — внешний ассет, в репозиторий её не кладём (размер, лицензия). Скачайте
официальную модель PoseLandmarker и положите файл сюда:

```
models/pose_landmarker.task
```

Проще всего — скриптом (качает вариант *lite* из официального хранилища
MediaPipe и кладёт под нужным именем):

```bash
bash scripts/fetch_model.sh
```

Вариант модели переопределяется переменной `ANALYTICS_MODEL_URL` (например, на
`pose_landmarker_full`/`pose_landmarker_heavy`). Прямой URL варианта *lite*:

```
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

Без файла модели воркер видеоаналитики не стартует (это ожидаемое требование
эксплуатации, не ошибка сборки).
