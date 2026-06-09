/* Оркестратор серверного анализа: кадры → analysis-core → события журнала.
 *
 * Это та же логика, что в браузере (live.html), но на сервере (Node). Источник
 * кадров (RTSP/файл + MediaPipe-извлечение поз) и приёмник событий (log-service)
 * — внешние адаптеры, они ИНЪЕКТИРУЮТСЯ. Благодаря этому ядро конвейера
 * детерминировано и покрывается Node-тестами без MediaPipe/сети.
 *
 * frames: async-итерируемый источник кадров. Каждый кадр:
 *   { lm, world?, ts? }  — lm: массив landmark-точек MediaPipe (норм. 0..1),
 *                          world: 3D-точки (для приседа/наклона), ts: мс.
 * sink:   async (journalEvent) => void — куда сложить готовое событие журнала
 *         (в проде — POST в log-service /events; в тестах — сбор в массив).
 */

import { AnalysisEngine } from '../../analysis-core/analysis-core.mjs';
import { toJournalEvent } from './payload.mjs';

export async function runAnalysis({ frames, engine, sink, roomId = null, cameraId = null, onRaw = null }) {
  const eng = engine ?? new AnalysisEngine();
  let framesProcessed = 0;
  let emitted = 0;

  for await (const frame of frames) {
    // engineNow — МОНОТОННОЕ время кадра (для таймингов активностей внутри движка);
    // wallTs — СТЕННЫЕ часы момента съёмки (идут в ts события журнала). Это два
    // разных времени: путать их нельзя, иначе события улетят в 1970-й год.
    const engineNow = frame.ts ?? framesProcessed * 33; // ~30 fps, если не задано
    const wallTs = frame.wallTs ?? Date.now();
    const raw = eng.analyze(frame.lm, frame.world ?? null, engineNow);
    framesProcessed++;
    for (const ev of raw) {
      if (onRaw) onRaw(ev); // для отладки/UI — все события движка, включая позы
      const journal = toJournalEvent(ev, { roomId, cameraId, ts: wallTs });
      if (journal) {
        await sink(journal);
        emitted++;
      }
    }
  }

  return { framesProcessed, emitted, coverage: eng.rois.map((r) => ({ type: r.type, name: r.name, cov: r.cov })) };
}

/* Приёмник, который шлёт события в log-service /events (как Python-воркер).
 * Используется в проде; в тестах подменяется массивом-сборщиком. */
export function logServiceSink(baseUrl, { fetchImpl = fetch } = {}) {
  const url = baseUrl.replace(/\/$/, '') + '/events';
  return async (event) => {
    const resp = await fetchImpl(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });
    if (!resp.ok) throw new Error('log-service /events вернул ' + resp.status);
  };
}
