/* Источники кадров для серверного анализа.
 *
 * Интерфейс источника: async-итерируемый объект, выдающий кадры вида
 *   { lm, world?, ts? }
 * где lm — массив landmark-точек MediaPipe Pose (нормализованные 0..1).
 *
 * Конвейер (runner.mjs) от источника не зависит — это позволяет тестировать
 * логику на готовых наборах поз и подключать реальные источники адаптерами.
 */

/* Простой источник из массива готовых кадров (для тестов и воспроизведения). */
export async function* arrayFrames(frames) {
  for (const f of frames) yield f;
}

/* Распаковка точки из формата браузерного рекордера packLM: [x,y,z,v]. */
function unpackLM(packed) {
  return packed ? packed.map((p) => ({ x: p[0], y: p[1], z: p[2], visibility: p[3] })) : null;
}

/* Источник кадров из ЗАПИСИ браузерного «Живого анализа» (кнопка «запись» в
 * live.html выгружает JSON {meta, frames:[{t, lm, w}]}). Позволяет прогнать ту
 * же запись через серверное ядро и получить идентичные события — проверяемо без
 * камеры/MediaPipe. На вход — распарсенный JSON записи ИЛИ просто массив кадров. */
export async function* recordingFrames(recording) {
  const frames = Array.isArray(recording) ? recording : recording?.frames;
  if (!Array.isArray(frames)) throw new Error("в записи нет массива frames");
  for (const f of frames) {
    const lm = unpackLM(f.lm);
    if (!lm) continue; // кадр без позы (трекинг не видел человека) — пропускаем
    yield { lm, world: unpackLM(f.w), ts: f.t };
  }
}

/* СТЫК (Фаза 3, требует проверки на хосте): источник кадров из RTSP/видеофайла
 * через MediaPipe PoseLandmarker в Node.
 *
 * Реализация намеренно не написана: извлечение кадров из RTSP (ffmpeg/go2rtc) и
 * запуск MediaPipe tasks-vision в Node — нетривиальны и НЕ проверяются в
 * CI-окружении ассистента (нужен реальный поток/камера и нативные зависимости).
 * Поэтому интерфейс зафиксирован, а наполнение согласуется отдельно — чтобы
 * результат можно было проверить на твоём хосте, а не «вслепую».
 *
 * Ожидаемая сигнатура будущей реализации:
 *   async function* mediapipeFrames({ source, fps, maxFrames }) -> {lm, world, ts}
 * где source — RTSP-URL или путь к файлу.
 */
export async function* mediapipeFrames() {
  throw new Error(
    'mediapipeFrames: источник RTSP/файл+MediaPipe ещё не реализован (Фаза 3, ' +
    'проверяется на хосте). Используй arrayFrames для готовых поз.',
  );
}
