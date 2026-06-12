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

/* Живой источник кадров (Фаза 3, #255): RTSP/видеофайл → ffmpeg → детектор поз.
 *
 * Конвейер: rawFrames (ffmpeg, сырые RGBA-кадры фиксированного размера) →
 * detector.detect(frame, ts) → {lm, world} → кадры контракта runner'а.
 * Кадры без позы пропускаются (как в Python-воркере), но учитываются в stats.
 *
 * detector инъектируется: в проде — MediaPipe PoseLandmarker в Node
 * (src/mediapipe.mjs), в тестах — фейк. framesImpl — источник сырых кадров
 * (по умолчанию ffmpeg; в тестах — синтетический генератор).
 */
export async function* mediapipeFrames({
  source,
  fps = 5,
  maxFrames = 150,
  detector,
  framesImpl,
  stats = {},
}) {
  if (!detector) throw new Error('mediapipeFrames: нужен detector (детектор поз)');
  if (!framesImpl) {
    // Ленивая загрузка: тестам с фейковым framesImpl модуль ffmpeg не нужен.
    ({ rawFrames: framesImpl } = await import('./ffmpeg.mjs'));
  }
  stats.framesRead = 0;
  stats.posesFound = 0;
  for await (const raw of framesImpl({ source, fps, maxFrames })) {
    stats.framesRead++;
    const pose = await detector.detect(raw, raw.ts);
    if (!pose || !pose.lm) continue; // в кадре нет человека
    stats.posesFound++;
    yield { lm: pose.lm, world: pose.world ?? null, ts: raw.ts, wallTs: raw.wallTs };
  }
}
