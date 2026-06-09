/* Тесты чистых примитивов ядра анализа (node:test, без внешних зависимостей). */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  countReversals, range, mean, std, inBand, motionShape, shapeText,
  clamp01, r4, angleAt, pip, dist, vis, handPoint,
} from '../analysis-core.mjs';

test('countReversals считает смены направления с зоной нечувствительности', () => {
  // монотонный рост — 0 разворотов
  assert.equal(countReversals([0, 1, 2, 3, 4], 0.001), 0);
  // вверх-вниз-вверх — 2 разворота
  assert.equal(countReversals([0, 1, 0, 1], 0.001), 2);
  // мелкие колебания внутри dz игнорируются
  assert.equal(countReversals([0, 0.0005, 0, 0.0005], 0.001), 0);
});

test('range/mean/std считают как ожидается', () => {
  assert.equal(range([1, 5, 3]), 4);
  assert.equal(mean([2, 4, 6]), 4);
  assert.equal(std([2, 2, 2]), 0);
  assert.ok(Math.abs(std([1, 3]) - 1) < 1e-9);
});

test('inBand: все значения строго внутри полосы', () => {
  assert.equal(inBand([0.2, 0.3, 0.4], 0.1, 0.5), true);
  assert.equal(inBand([0.2, 0.6], 0.1, 0.5), false);
});

test('clamp01 и r4', () => {
  assert.equal(clamp01(-1), 0);
  assert.equal(clamp01(2), 1);
  assert.equal(clamp01(0.4), 0.4);
  assert.equal(r4(0.123456), 0.1235);
  assert.equal(r4(null), 0);
});

test('motionShape: круговая траектория → circle, линейная → line', () => {
  // окружность из 24 точек
  const xs = [], ys = [];
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * 2 * Math.PI;
    xs.push(0.5 + 0.1 * Math.cos(a));
    ys.push(0.5 + 0.1 * Math.sin(a));
  }
  assert.equal(motionShape(xs, ys), 'circle');
  // горизонтальная линия туда-обратно
  const lx = [0.1, 0.2, 0.3, 0.4, 0.3, 0.2, 0.1, 0.2];
  const ly = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5];
  assert.equal(motionShape(lx, ly), 'line');
  // слишком мало точек → line
  assert.equal(motionShape([0, 1], [0, 1]), 'line');
});

test('shapeText переводит код формы в русский', () => {
  assert.equal(shapeText('circle'), 'по кругу');
  assert.equal(shapeText('mixed'), 'разнонаправленно');
  assert.equal(shapeText('line'), 'вперёд-назад');
});

test('angleAt: прямой угол ≈ 90°, развёрнутый ≈ 180°', () => {
  const b = { x: 0, y: 0, z: 0 };
  const a = { x: 1, y: 0, z: 0 };
  const c = { x: 0, y: 1, z: 0 };
  assert.ok(Math.abs(angleAt(a, b, c) - 90) < 1e-6);
  const c2 = { x: -1, y: 0, z: 0 };
  assert.ok(Math.abs(angleAt(a, b, c2) - 180) < 1e-6);
});

test('pip: точка-в-многоугольнике (квадрат)', () => {
  const sq = [[0, 0], [1, 0], [1, 1], [0, 1]];
  assert.equal(pip(0.5, 0.5, sq), true);
  assert.equal(pip(1.5, 0.5, sq), false);
  assert.equal(pip(-0.1, 0.5, sq), false);
});

test('dist и vis', () => {
  assert.equal(dist({ x: 0, y: 0 }, { x: 3, y: 4 }), 5);
  assert.equal(vis({ x: 0, y: 0 }), 1);
  assert.equal(vis({ x: 0, y: 0, visibility: 0.3 }), 0.3);
  assert.equal(vis(null), null);
});

test('handPoint продлевает локоть→запястье за запястье', () => {
  const lm = [];
  lm[16] = { x: 0.5, y: 0.5 }; // правое запястье
  lm[14] = { x: 0.4, y: 0.5 }; // правый локоть
  const p = handPoint(lm, 16);
  // продление на 0.45 за запястье по направлению от локтя
  assert.ok(Math.abs(p.x - (0.5 + 0.1 * 0.45)) < 1e-9);
  assert.equal(p.y, 0.5);
});
