/* Тесты цикла Node-воркера (фейки вместо БД/ffmpeg/MediaPipe). */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { TABLE, wipingFrames } from '../../analysis-core/test/fixtures.mjs';
import { arrayFrames, mediapipeFrames } from '../src/sources.mjs';
import { engineEnabledFromToggles, runForever, runOnce, SERVICE_NAME } from '../src/worker.mjs';

const TASK = {
  id: 'task-1',
  source_type: 'stream',
  source_ref: 'rtsp://media-gateway:8554/cam-01',
  room_id: 'room-01',
  camera_id: 'cam-uuid',
  pipeline: 'pose_v1',
  params: null,
};

/* Фейковый query под сценарий: claim отдаёт задание один раз, потом пусто. */
function fakeQ({ task = TASK, camera, zones = [] } = {}) {
  let claimed = false;
  const calls = [];
  const q = async (sql, params) => {
    calls.push({ sql, params });
    if (sql.includes('FOR UPDATE SKIP LOCKED')) {
      if (claimed || !task) return { rows: [] };
      claimed = true;
      return { rows: [task] };
    }
    if (sql.includes('FROM cameras')) return { rows: camera ? [camera] : [] };
    if (sql.includes('FROM camera_zones')) return { rows: zones };
    return { rows: [] };
  };
  q.calls = calls;
  return q;
}

const tableZoneRow = { id: 7, zone_type: 'table', polygon: TABLE.pts, note: 'стол' };

test('runOnce: задание → события протирки и coverage → done со сводкой', async () => {
  const q = fakeQ({ zones: [tableZoneRow] });
  const events = [];
  const processed = await runOnce({
    q,
    framesFactory: () => arrayFrames(wipingFrames()),
    sink: async (ev) => events.push(ev),
    log: () => {},
  });

  assert.equal(processed, true);
  assert.ok(events.length > 0, 'ожидались события журнала');
  assert.ok(events.some((e) => e.type === 'action_detected'));
  assert.ok(events.some((e) => e.type === 'coverage_report'));

  const done = q.calls.find((c) => c.sql.includes("status = 'done'"));
  assert.ok(done, 'задание должно завершиться done');
  const result = JSON.parse(done.params[1]);
  assert.ok(result.events >= events.length);
  assert.equal(result.artifact, null);
  assert.ok(result.coverage_zones >= 1);
});

test('runOnce: выключенная камера — done без обработки кадров', async () => {
  const q = fakeQ({ camera: { id: 'cam-uuid', enabled: false, analytics: null } });
  let framesAsked = false;
  const processed = await runOnce({
    q,
    framesFactory: () => {
      framesAsked = true;
      return arrayFrames([]);
    },
    sink: async () => {},
    log: () => {},
  });
  assert.equal(processed, true);
  assert.equal(framesAsked, false, 'кадры не должны были запрашиваться');
  const done = q.calls.find((c) => c.sql.includes("status = 'done'"));
  assert.deepEqual(JSON.parse(done.params[1]), {
    frames: 0, poses: 0, events: 0, coverage_zones: 0, artifact: null,
  });
});

test('runOnce: ошибка источника кадров → failed, воркер жив', async () => {
  const q = fakeQ();
  const processed = await runOnce({
    q,
    framesFactory: () => {
      throw new Error('ffmpeg не выдал ни одного кадра');
    },
    sink: async () => {},
    log: () => {},
  });
  assert.equal(processed, true);
  const failed = q.calls.find((c) => c.sql.includes("status = 'failed'"));
  assert.match(failed.params[1], /ffmpeg/);
});

test('runOnce: пустая очередь — false (сигнал поспать)', async () => {
  const q = fakeQ({ task: null });
  assert.equal(await runOnce({ q, framesFactory: () => arrayFrames([]), sink: async () => {} }), false);
});

test('runForever: heartbeat на итерации, сон при пустой очереди, остановка по сигналу', async () => {
  const q = fakeQ({ task: null });
  const sleeps = [];
  let stops = 0;
  await runForever({
    q,
    framesFactory: () => arrayFrames([]),
    sink: async () => {},
    sleep: async (ms) => sleeps.push(ms),
    shouldStop: () => ++stops > 2, // две итерации, на третьей — стоп
    log: () => {},
    maxIterations: 10,
  });
  const beats = q.calls.filter((c) => c.sql.includes('service_heartbeats'));
  assert.equal(beats.length, 2);
  assert.deepEqual(beats[0].params[0], SERVICE_NAME);
  assert.deepEqual(sleeps, [5000, 5000]);
});

test('тумблеры камеры → карта детекторов движка', () => {
  const all = engineEnabledFromToggles(null);
  assert.equal(all.wipe, true);
  assert.equal(all.arms, true);
  assert.equal(all.presence, false);

  const noActions = engineEnabledFromToggles({ actions: false });
  assert.equal(noActions.wipe, false);
  assert.equal(noActions.arms, true);

  const noPose = engineEnabledFromToggles({ pose: false });
  assert.equal(noPose.arms, false);
  assert.equal(noPose.wipe, true);
});

test('mediapipeFrames: пропускает кадры без позы и ведёт статистику', async () => {
  const raw = [
    { data: new Uint8ClampedArray(4), width: 1, height: 1, ts: 0, wallTs: 1000 },
    { data: new Uint8ClampedArray(4), width: 1, height: 1, ts: 200, wallTs: 1200 },
    { data: new Uint8ClampedArray(4), width: 1, height: 1, ts: 400, wallTs: 1400 },
  ];
  // Поза находится только во втором кадре.
  const detector = {
    detect: async (frame, ts) => (ts === 200 ? { lm: [{ x: 0.5, y: 0.5, z: 0 }], world: null } : null),
  };
  const stats = {};
  const got = [];
  for await (const f of mediapipeFrames({
    source: 'rtsp://cam',
    detector,
    framesImpl: async function* () {
      yield* raw;
    },
    stats,
  })) {
    got.push(f);
  }
  assert.equal(got.length, 1);
  assert.deepEqual(got[0].ts, 200);
  assert.equal(got[0].wallTs, 1200);
  assert.deepEqual(stats, { framesRead: 3, posesFound: 1 });
});
