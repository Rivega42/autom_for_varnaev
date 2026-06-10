/* Тесты воспроизведения записи: формат браузерного рекордера → серверное ядро
 * даёт те же события. Та же синтетическая «протирка стола», но упакованная как
 * запись live.html (packLM), плюс прогон CLI-обёртки. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TABLE, wipingFrames } from "../../analysis-core/test/fixtures.mjs";
import { recordingFrames } from "../src/sources.mjs";
import { runAnalysis } from "../src/runner.mjs";
import { AnalysisEngine } from "../../analysis-core/analysis-core.mjs";
import { cliMain } from "../bin/analyze.mjs";

/* fixtures.wipingFrames() → формат записи рекордера: {meta, frames:[{t,lm,w}]}. */
function asRecording() {
  const pack = (lm) => lm.map((p) => [p.x, p.y, p.z, p.visibility == null ? 1 : p.visibility]);
  const frames = wipingFrames().map((f) => ({ t: f.ts, lm: pack(f.lm), w: null }));
  return { meta: { frames: frames.length, mirror: false }, frames };
}

test("recordingFrames распаковывает packLM в точки движка", async () => {
  const rec = asRecording();
  const out = [];
  for await (const fr of recordingFrames(rec)) out.push(fr);
  assert.equal(out.length, rec.frames.length);
  assert.equal(typeof out[0].lm[0].x, "number");
  assert.equal(out[0].lm[0].visibility, 1);
});

test("запись «протирки» через ядро даёт старт и покрытие", async () => {
  const engine = new AnalysisEngine({ rois: [TABLE] });
  const sink = [];
  const summary = await runAnalysis({
    frames: recordingFrames(asRecording()),
    engine,
    sink: async (e) => sink.push(e),
    roomId: "room-1",
    cameraId: "cam-9",
  });
  assert.equal(summary.framesProcessed, 140);
  assert.ok(sink.some((e) => e.type === "action_detected" && e.message.startsWith("Начато протирание стола")));
  const cov = sink.find((e) => e.type === "coverage_report");
  assert.ok(cov && cov.payload.zone === "table" && cov.payload.coverage_pct > 0);
});

test("cliMain читает файл записи и зоны, собирает события через sink", async () => {
  const dir = await mkdtemp(join(tmpdir(), "replay-"));
  const recPath = join(dir, "rec.json");
  const zonesPath = join(dir, "zones.json");
  await writeFile(recPath, JSON.stringify(asRecording()));
  // формат API GET /cameras/{id}/zones
  await writeFile(zonesPath, JSON.stringify({ items: [{ id: 7, zone_type: "table", polygon: TABLE.pts }] }));

  const sink = [];
  const summary = await cliMain(
    { recording: recPath, zones: zonesPath, room: "room-1", camera: "cam-9" },
    { sink: async (e) => sink.push(e), log: () => {} },
  );
  assert.equal(summary.framesProcessed, 140);
  assert.ok(sink.some((e) => e.type === "coverage_report" && e.payload.zone_id === 7));
});

test("cliMain принимает зоны в полном конверте API ({status,data:{items}})", async () => {
  const dir = await mkdtemp(join(tmpdir(), "replay-env-"));
  const recPath = join(dir, "rec.json");
  const zonesPath = join(dir, "zones.json");
  await writeFile(recPath, JSON.stringify(asRecording()));
  // как сохраняет curl: полный конверт ответа api-gateway
  await writeFile(zonesPath, JSON.stringify({
    status: "ok", error: null, ts: "2026-06-09T00:00:00Z",
    data: { items: [{ id: 7, zone_type: "table", polygon: TABLE.pts }] },
  }));

  const sink = [];
  await cliMain(
    { recording: recPath, zones: zonesPath, room: "room-1" },
    { sink: async (e) => sink.push(e), log: () => {} },
  );
  assert.ok(sink.some((e) => e.type === "coverage_report" && e.payload.zone_id === 7));
});
