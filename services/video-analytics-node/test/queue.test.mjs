/* Тесты протокола очереди analysis_tasks (без Postgres — фейковый query). */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  claimNextTask,
  loadCameraZones,
  markDone,
  markFailed,
  writeHeartbeat,
} from '../src/queue.mjs';

/* Фейковый query: пишет вызовы в журнал, отвечает по подстроке SQL. */
function fakeQuery(responses = {}) {
  const calls = [];
  const q = async (sql, params) => {
    calls.push({ sql, params });
    for (const [needle, rows] of Object.entries(responses)) {
      if (sql.includes(needle)) return { rows };
    }
    return { rows: [] };
  };
  q.calls = calls;
  return q;
}

test('claim: задание берётся в транзакции с SKIP LOCKED и переводится в running', async () => {
  const task = { id: 'task-1', source_type: 'stream', source_ref: 'rtsp://x' };
  const q = fakeQuery({ 'FOR UPDATE SKIP LOCKED': [task] });

  const claimed = await claimNextTask(q, '2026-06-12T10:00:00Z');

  assert.equal(claimed, task);
  const sqls = q.calls.map((c) => c.sql);
  assert.equal(sqls[0], 'BEGIN');
  assert.match(sqls[1], /FOR UPDATE SKIP LOCKED/);
  assert.match(sqls[2], /SET status = 'running', started_at = \$1/);
  assert.deepEqual(q.calls[2].params, ['2026-06-12T10:00:00Z', 'task-1']);
  assert.equal(sqls[3], 'COMMIT');
});

test('claim: пустая очередь — null и COMMIT (транзакция не висит)', async () => {
  const q = fakeQuery();
  assert.equal(await claimNextTask(q, '2026-06-12T10:00:00Z'), null);
  assert.deepEqual(q.calls.map((c) => c.sql).filter((s) => s === 'COMMIT').length, 1);
});

test('claim: ошибка внутри транзакции — ROLLBACK и проброс', async () => {
  const q = async (sql) => {
    q.calls.push(sql);
    if (sql.includes('FOR UPDATE')) throw new Error('БД упала');
    return { rows: [] };
  };
  q.calls = [];
  await assert.rejects(() => claimNextTask(q, 'now'), /БД упала/);
  assert.ok(q.calls.includes('ROLLBACK'));
});

test('markDone/markFailed: статус, finished_at и result/error', async () => {
  const q = fakeQuery();
  await markDone(q, 'task-1', 'ts1', { frames: 10 });
  await markFailed(q, 'task-2', 'ts2', new Error('камера недоступна'));

  assert.match(q.calls[0].sql, /status = 'done'/);
  assert.deepEqual(q.calls[0].params, ['ts1', '{"frames":10}', 'task-1']);
  assert.match(q.calls[1].sql, /status = 'failed'/);
  assert.match(q.calls[1].params[1], /камера недоступна/);
});

test('heartbeat: upsert по имени сервиса', async () => {
  const q = fakeQuery();
  await writeHeartbeat(q, 'video-analytics-node', 'ts');
  assert.match(q.calls[0].sql, /ON CONFLICT \(service\) DO UPDATE/);
  assert.deepEqual(q.calls[0].params, ['video-analytics-node', 'ts']);
});

test('зоны: формат движка, forbidden/work отфильтрованы, polygon из строки', async () => {
  const q = fakeQuery({
    'FROM camera_zones': [
      { id: 7, zone_type: 'table', polygon: '[[0,0],[1,0],[1,1]]', note: 'стол' },
      { id: 8, zone_type: 'forbidden', polygon: [[0, 0], [1, 0], [1, 1]], note: null },
      { id: 9, zone_type: 'floor', polygon: [[0, 0], [1, 0], [0, 1]], note: null },
    ],
  });
  const rois = await loadCameraZones(q, 'cam-uuid');
  assert.deepEqual(rois.map((r) => r.zoneId), [7, 9]);
  assert.deepEqual(rois[0], {
    type: 'table',
    pts: [[0, 0], [1, 0], [1, 1]],
    zoneId: 7,
    name: 'стол',
    cov: 0,
  });
  assert.equal(rois[1].name, 'floor'); // note=null -> имя по типу зоны
});
