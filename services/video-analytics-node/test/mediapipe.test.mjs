/* Тесты обёртки лэндмаркера (фейк вместо MediaPipe/WebGL — их в CI нет). */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import { wrapLandmarker } from '../src/mediapipe.mjs';

// Минимальный ImageData: в проде его ставит installGlobals (вместе с WebGL),
// здесь достаточно формы {data, width, height}.
if (!globalThis.ImageData) {
  globalThis.ImageData = class ImageData {
    constructor(data, width, height) {
      this.data = data;
      this.width = width;
      this.height = height;
    }
  };
}

const FRAME = { data: new Uint8ClampedArray(4), width: 1, height: 1 };

function fakeLandmarker(results) {
  return {
    calls: [],
    closed: false,
    detectForVideo(img, ts) {
      this.calls.push({ img, ts });
      return results.shift() ?? { landmarks: [] };
    },
    close() {
      this.closed = true;
    },
  };
}

test('detect: маппинг landmarks/world в контракт кадра', async () => {
  const fake = fakeLandmarker([
    {
      landmarks: [[{ x: 0.1, y: 0.2, z: 0.3, visibility: 0.9 }]],
      worldLandmarks: [[{ x: 1, y: 2, z: 3 }]],
    },
  ]);
  const det = wrapLandmarker(fake);
  const pose = await det.detect(FRAME, 100);
  assert.deepEqual(pose.lm, [{ x: 0.1, y: 0.2, z: 0.3, visibility: 0.9 }]);
  assert.deepEqual(pose.world, [{ x: 1, y: 2, z: 3 }]);
  assert.equal(fake.calls[0].img.width, 1);
});

test('detect: пустые landmarks -> null (кадр без человека)', async () => {
  const det = wrapLandmarker(fakeLandmarker([{ landmarks: [] }]));
  assert.equal(await det.detect(FRAME, 1), null);
});

test('detect: timestamp строго возрастает даже при равных ts кадров', async () => {
  const fake = fakeLandmarker([{ landmarks: [] }, { landmarks: [] }, { landmarks: [] }]);
  const det = wrapLandmarker(fake);
  await det.detect(FRAME, 100);
  await det.detect(FRAME, 100); // тот же ts источника
  await det.detect(FRAME, 50); // и даже откат назад
  assert.deepEqual(fake.calls.map((c) => c.ts), [100, 101, 102]);
});

test('close проксируется в лэндмаркер', () => {
  const fake = fakeLandmarker([]);
  wrapLandmarker(fake).close();
  assert.equal(fake.closed, true);
});
