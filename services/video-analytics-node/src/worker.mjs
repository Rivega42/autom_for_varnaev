/* Цикл Node-воркера видеоаналитики: очередь analysis_tasks → analysis-core → журнал.
 *
 * Повторяет протокол Python-воркера (services/video-analytics): claim →
 * анализ → события в log-service → done/failed; heartbeat на каждой итерации;
 * мягкая остановка между заданиями. Все внешние зависимости (БД, источник
 * кадров, приёмник событий, часы) инъектируются — цикл тестируется без
 * Postgres/ffmpeg/MediaPipe.
 *
 * Ограничения Фазы 3 (до вывода Python-детекторов, #255 шаг 3):
 * - события: action_detected и coverage_report (ядро PoC); uniform_violation,
 *   presence_detected/forbidden_zone_entry остаются за Python-воркером;
 * - скриншот-артефакт не сохраняется (result.artifact = null) — рендер кадра
 *   с заливкой в Node будет добавлен отдельно.
 */

import { AnalysisEngine } from '../../analysis-core/analysis-core.mjs';
import { claimNextTask, loadCamera, loadCameraZones, markDone, markFailed, writeHeartbeat } from './queue.mjs';
import { runAnalysis } from './runner.mjs';

/* Имя сервиса в service_heartbeats: своё, чтобы watchdog (#284) различал
 * Python- и Node-воркеры при параллельной полевой проверке. */
export const SERVICE_NAME = 'video-analytics-node';

/* Карта тумблеров камеры (cameras.analytics: {pose,actions,coverage,...}) →
 * карта enabled движка. null/отсутствие ключа = включено (как в Python). */
export function engineEnabledFromToggles(analytics) {
  const t = analytics ?? {};
  const on = (key) => t[key] !== false;
  const enabled = {};
  // Позы/положения тела — детекторы группы pose.
  for (const k of ['arms', 'legs', 'head', 'torso', 'still']) enabled[k] = on('pose');
  // Действия (уборка, жесты, тревоги) — группа actions.
  for (const k of ['wipe', 'mop', 'sweep', 'window', 'wave', 'clap', 'walk', 'fall', 'sos']) {
    enabled[k] = on('actions');
  }
  // presence в ядре нет (детектирует хост) — выключаем для ясности.
  enabled.presence = false;
  return enabled;
}

/* Одна итерация: взять задание и обработать. Возвращает true, если задание
 * было (false = очередь пуста, можно поспать). Ошибка обработки переводит
 * задание в failed и НЕ роняет воркер. */
export async function runOnce({
  q,
  framesFactory,
  sink,
  now = () => new Date(),
  log = console.error,
}) {
  const task = await claimNextTask(q, now().toISOString());
  if (!task) return false;

  try {
    // Тумблеры аналитики камеры; выключенная камера = пустой прогон (как в Python:
    // события подавлены), задание закрывается без обработки кадров.
    const camera = task.camera_id ? await loadCamera(q, task.camera_id) : null;
    if (camera && camera.enabled === false) {
      await markDone(q, task.id, now().toISOString(), {
        frames: 0, poses: 0, events: 0, coverage_zones: 0, artifact: null,
      });
      log(`Задание ${task.id}: камера выключена — пропуск без обработки`);
      return true;
    }

    const rois = task.camera_id ? await loadCameraZones(q, task.camera_id) : [];
    const engine = new AnalysisEngine({
      rois,
      enabled: engineEnabledFromToggles(camera?.analytics),
    });

    // stats наполняет источник кадров: кадров прочитано/с позой (для result).
    const stats = { framesRead: 0, posesFound: 0 };
    const frames = framesFactory(task, stats);
    const summary = await runAnalysis({
      frames,
      engine,
      sink,
      roomId: task.room_id,
      cameraId: task.camera_id,
    });

    await markDone(q, task.id, now().toISOString(), {
      frames: stats.framesRead || summary.framesProcessed,
      poses: stats.posesFound || summary.framesProcessed,
      events: summary.emitted,
      coverage_zones: summary.coverage.filter((c) => c.cov > 0).length,
      artifact: null,
    });
    log(`Задание ${task.id}: done (кадров=${summary.framesProcessed}, событий=${summary.emitted})`);
  } catch (err) {
    await markFailed(q, task.id, now().toISOString(), err?.message ?? err);
    log(`Задание ${task.id}: failed — ${err?.message ?? err}`);
  }
  return true;
}

/* Бесконечный цикл: heartbeat → задание; пустая очередь — сон idle_sleep.
 * shouldStop проверяется между заданиями (текущее не прерывается), sleep
 * в проде — stop.wait-подобная прерываемая пауза. */
export async function runForever({
  q,
  framesFactory,
  sink,
  idleSleepMs = 5000,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  shouldStop = () => false,
  now = () => new Date(),
  log = console.error,
  maxIterations = Infinity,
}) {
  for (let i = 0; i < maxIterations; i++) {
    if (shouldStop()) {
      log('Node-воркер: получен сигнал остановки — выходим из цикла');
      return;
    }
    try {
      await writeHeartbeat(q, SERVICE_NAME, now().toISOString());
    } catch (err) {
      log(`heartbeat не записан: ${err?.message ?? err}`); // не фатально
    }
    let processed = false;
    try {
      processed = await runOnce({ q, framesFactory, sink, now, log });
    } catch (err) {
      // Сбой claim'а (например, отвалилась БД) — не роняем процесс.
      log(`итерация воркера: ${err?.message ?? err}`);
    }
    if (!processed) await sleep(idleSleepMs);
  }
}
