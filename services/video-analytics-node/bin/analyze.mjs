#!/usr/bin/env node
/* CLI воспроизведения записи браузерного анализа через серверное ядро.
 *
 * Замыкает цикл «записал в браузере → прогнал на сервере тем же ядром»:
 *   node bin/analyze.mjs --recording skeleton-*.json --room room-01 \
 *        [--camera <uuid>] [--zones zones.json] \
 *        [--post http://log-service:8000] [--api-key KEY]
 *
 * Без --post события печатаются в stdout (JSON-строки) — удобно для проверки.
 * Источник кадров здесь — ЗАПИСЬ (без MediaPipe/RTSP); реальный live-источник
 * (mediapipeFrames) подключается на хосте отдельно. Только Node-builtins.
 */

import { readFile } from "node:fs/promises";
import { AnalysisEngine } from "../../analysis-core/analysis-core.mjs";
import { runAnalysis, logServiceSink } from "../src/runner.mjs";
import { recordingFrames } from "../src/sources.mjs";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) args[a.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
  }
  return args;
}

/* зоны в формате API (GET /cameras/{id}/zones → items[{id,zone_type,polygon}])
 * или уже в формате ядра ([{type,pts}]) → ROI ядра. */
function toRois(zones) {
  return (zones || []).map((z) => ({
    type: z.zone_type ?? z.type,
    pts: z.polygon ?? z.pts,
    zoneId: z.id ?? z.zoneId,
    name: z.note ?? z.name,
    cov: 0,
  }));
}

export async function cliMain(args, { sink, log = console.error } = {}) {
  if (!args.recording) throw new Error("нужен --recording <файл записи .json>");
  const recording = JSON.parse(await readFile(args.recording, "utf-8"));
  const zones = args.zones ? JSON.parse(await readFile(args.zones, "utf-8")) : [];
  const rois = toRois(Array.isArray(zones) ? zones : zones.items);

  if (args.post === true) throw new Error("--post требует URL log-service");
  const engine = new AnalysisEngine({ rois });
  const out = sink ?? (typeof args.post === "string"
    ? logServiceSink(args.post)
    : async (e) => process.stdout.write(JSON.stringify(e) + "\n"));

  const summary = await runAnalysis({
    frames: recordingFrames(recording),
    engine,
    sink: out,
    roomId: args.room ?? null,
    cameraId: args.camera ?? null,
  });
  log(
    `Готово: кадров ${summary.framesProcessed}, событий в журнал ${summary.emitted}` +
    (rois.length ? `, покрытие ${summary.coverage.map((r) => `${r.name || r.type} ${r.cov}%`).join(", ")}` : ""),
  );
  return summary;
}

// Запуск как скрипт (не при импорте в тестах).
if (import.meta.url === `file://${process.argv[1]}`) {
  cliMain(parseArgs(process.argv.slice(2))).catch((e) => {
    process.stderr.write("Ошибка: " + e.message + "\n");
    process.exit(1);
  });
}
