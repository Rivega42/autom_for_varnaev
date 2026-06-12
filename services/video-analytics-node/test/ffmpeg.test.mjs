/* Тесты нарезки rawvideo-потока ffmpeg на кадры (без реального ffmpeg). */

import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { Readable } from 'node:stream';
import { test } from 'node:test';

import { buildFfmpegArgs, rawFrames } from '../src/ffmpeg.mjs';

/* Фейковый процесс: stdout отдаёт заданные чанки, stderr пуст. */
function fakeProc(chunks) {
  const proc = new EventEmitter();
  proc.stdout = Readable.from(chunks);
  proc.stderr = new Readable({ read() { this.push(null); } });
  proc.killed = [];
  proc.kill = (sig) => proc.killed.push(sig);
  return proc;
}

test('args: RTSP идёт по TCP, файл — без rtsp_transport; rawvideo rgba', () => {
  const rtsp = buildFfmpegArgs({ source: 'rtsp://cam/1', fps: 5, width: 64, height: 36 });
  assert.deepEqual(rtsp.slice(0, 2), ['-rtsp_transport', 'tcp']);
  assert.ok(rtsp.includes('rawvideo') && rtsp.includes('rgba'));
  assert.ok(rtsp.includes('fps=5,scale=64:36'));

  const file = buildFfmpegArgs({ source: '/data/v.mp4', fps: 5, width: 64, height: 36 });
  assert.equal(file[0], '-i');
});

test('кадры режутся по границе w*h*4 даже из невыровненных чанков', async () => {
  const w = 4;
  const h = 2;
  const frameSize = w * h * 4; // 32 байта
  // 2.5 кадра тремя неровными чанками: третий кадр неполный — отбрасывается.
  const bytes = Buffer.alloc(frameSize * 2.5, 1);
  const chunks = [bytes.subarray(0, 10), bytes.subarray(10, 50), bytes.subarray(50)];
  const proc = fakeProc(chunks);

  const got = [];
  for await (const frame of rawFrames({
    source: 'rtsp://cam/1',
    fps: 10,
    width: w,
    height: h,
    spawnImpl: () => proc,
  })) {
    got.push(frame);
  }

  assert.equal(got.length, 2);
  assert.equal(got[0].data.length, frameSize);
  assert.ok(got[0].data instanceof Uint8ClampedArray);
  // Монотонные ts по индексу кадра и fps: 0, 100 мс при fps=10.
  assert.deepEqual(got.map((f) => f.ts), [0, 100]);
  assert.ok(got[0].wallTs > 0);
  // По закрытии генератора процесс гасится.
  assert.deepEqual(proc.killed, ['SIGKILL']);
});

test('maxFrames останавливает чтение и убивает процесс', async () => {
  const w = 2;
  const h = 2;
  const frameSize = w * h * 4;
  const proc = fakeProc([Buffer.alloc(frameSize * 5, 7)]);

  const got = [];
  for await (const frame of rawFrames({
    source: '/data/v.mp4',
    width: w,
    height: h,
    maxFrames: 3,
    spawnImpl: () => proc,
  })) {
    got.push(frame);
  }
  assert.equal(got.length, 3);
  assert.deepEqual(proc.killed, ['SIGKILL']);
});

test('ни одного кадра — ошибка с диагностикой', async () => {
  const proc = fakeProc([]);
  await assert.rejects(async () => {
    // eslint-disable-next-line no-unused-vars
    for await (const _ of rawFrames({ source: 'rtsp://dead', spawnImpl: () => proc })) {
      // недостижимо
    }
  }, /не выдал ни одного кадра/);
});
