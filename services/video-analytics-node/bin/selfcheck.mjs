#!/usr/bin/env node
/* Самопроверка живого конвейера на хосте/объекте (#255).
 *
 * Прогоняет источник (RTSP-URL или видеофайл) через полную цепочку
 * ffmpeg → MediaPipe (Node) → analysis-core и печатает сводку. События
 * журнала НЕ отправляются — только подсчёт (безопасно гонять на объекте).
 *
 *   node bin/selfcheck.mjs rtsp://media-gateway:8554/cam-01 [--frames 50] [--fps 5]
 *   node bin/selfcheck.mjs /tmp/test.mp4
 *
 * Пути к ассетам MediaPipe и модели — из тех же переменных окружения, что у
 * боевого воркера (MEDIAPIPE_*, ANALYTICS_MODEL_PATH).
 */

import process from 'node:process';

import { AnalysisEngine } from '../../analysis-core/analysis-core.mjs';
import { createPoseDetector } from '../src/mediapipe.mjs';
import { runAnalysis } from '../src/runner.mjs';
import { mediapipeFrames } from '../src/sources.mjs';

const env = (key, fallback) => process.env[key] ?? fallback;

const args = process.argv.slice(2);
const source = args.find((a) => !a.startsWith('--'));
if (!source) {
  console.error('Использование: node bin/selfcheck.mjs <rtsp-url|видеофайл> [--frames N] [--fps N]');
  process.exit(2);
}
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? Number(args[i + 1]) : fallback;
};
const maxFrames = flag('frames', 50);
const fps = flag('fps', 5);

console.error(`[selfcheck] источник: ${source}, кадров: ${maxFrames}, fps: ${fps}`);
console.error('[selfcheck] загрузка MediaPipe...');
const detector = await createPoseDetector({
  modelPath: env('ANALYTICS_MODEL_PATH', '/models/pose_landmarker.task'),
  wasmDir: env('MEDIAPIPE_WASM_DIR', '/app/services/video-analytics-node/node_modules/@mediapipe/tasks-vision/wasm'),
  bundlePath: env('MEDIAPIPE_BUNDLE', '/app/services/video-analytics-node/node_modules/@mediapipe/tasks-vision/vision_bundle.mjs'),
});

const stats = {};
const events = [];
const t0 = performance.now();
const summary = await runAnalysis({
  frames: mediapipeFrames({ source, fps, maxFrames, detector, stats }),
  engine: new AnalysisEngine(),
  sink: async (ev) => events.push(ev),
  roomId: 'selfcheck',
});
const elapsed = ((performance.now() - t0) / 1000).toFixed(1);

detector.close?.();
console.error(
  `[selfcheck] за ${elapsed} с: кадров прочитано=${stats.framesRead}, с позой=${stats.posesFound}, ` +
  `событий журнала=${summary.emitted}`,
);
for (const ev of events) console.log(JSON.stringify(ev));
console.error('[selfcheck] ГОТОВО');
process.exit(0); // wasm/GL держат хэндлы — выходим явно
