#!/usr/bin/env node
/* Точка входа Node-воркера видеоаналитики (продакшен, #255).
 *
 * Собирает боевые зависимости и запускает цикл очереди analysis_tasks:
 *   pg (TimescaleDB) + MediaPipe PoseLandmarker (Node) + ffmpeg (кадры) +
 *   log-service (события журнала).
 *
 * Тесты этот файл НЕ импортируют (pg ставится только в образе, npm install);
 * логика цикла — в src/worker.mjs и покрыта тестами на фейках.
 *
 * Переменные окружения — те же, что у Python-воркера (docker-compose.yml),
 * плюс пути к вендоренным ассетам MediaPipe (заданы в Dockerfile).
 */

import process from 'node:process';

import pg from 'pg';

import { createPoseDetector } from '../src/mediapipe.mjs';
import { logServiceSink } from '../src/runner.mjs';
import { mediapipeFrames } from '../src/sources.mjs';
import { runForever } from '../src/worker.mjs';

const env = (key, fallback) => process.env[key] ?? fallback;

async function main() {
  const client = new pg.Client({
    host: env('POSTGRES_HOST', 'db'),
    port: Number(env('POSTGRES_PORT', '5432')),
    database: env('POSTGRES_DB', 'monitoring'),
    user: env('POSTGRES_USER', 'monitoring'),
    password: env('POSTGRES_PASSWORD', ''),
  });
  await client.connect();
  const q = (sql, params) => client.query(sql, params);

  const detector = await createPoseDetector({
    modelPath: env('ANALYTICS_MODEL_PATH', '/models/pose_landmarker.task'),
    wasmDir: env('MEDIAPIPE_WASM_DIR', '/app/vendor/mediapipe/wasm'),
    bundlePath: env('MEDIAPIPE_BUNDLE', '/app/vendor/mediapipe/vision_bundle.mjs'),
  });

  const fps = Number(env('ANALYTICS_FPS', '5'));
  const maxStreamFrames = Number(env('ANALYTICS_MAX_STREAM_FRAMES', '150'));
  const sink = logServiceSink(env('LOG_SERVICE_URL', 'http://log-service:8000'));

  // Мягкая остановка (#206): docker stop шлёт SIGTERM — цикл выходит между
  // заданиями (сон при пустой очереди не дольше idleSleepMs).
  let stopping = false;
  const requestStop = (sig) => {
    console.error(`Получен сигнал ${sig} — мягкая остановка`);
    stopping = true;
  };
  process.on('SIGTERM', () => requestStop('SIGTERM'));
  process.on('SIGINT', () => requestStop('SIGINT'));

  // RTSP-задания ограничиваются по кадрам (живой поток бесконечен), файл
  // читается целиком — как в Python-воркере.
  const framesFactory = (task, stats) =>
    mediapipeFrames({
      source: task.source_ref,
      fps,
      maxFrames: task.source_type === 'stream' ? maxStreamFrames : Infinity,
      detector,
      stats,
    });

  console.error(
    `Node-воркер видеоаналитики запущен: модель=${env('ANALYTICS_MODEL_PATH', '/models/pose_landmarker.task')}, ` +
    `fps=${fps}, лимит stream=${maxStreamFrames}`,
  );
  try {
    await runForever({ q, framesFactory, sink, shouldStop: () => stopping });
  } finally {
    await client.end();
    detector.close?.();
    console.error('Node-воркер остановлен штатно');
  }
}

main().catch((err) => {
  console.error('Фатальная ошибка Node-воркера:', err);
  process.exit(1);
});
