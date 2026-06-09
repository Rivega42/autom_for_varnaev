/* Дымовой тест движка: синтетическая «протирка стола» правой рукой должна дать
 * событие «Начато протирание стола…», а после остановки — финал с покрытием зоны.
 * Так мы проверяем, что перенесённая из PoC стейт-машина и расчёт покрытия живые. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { AnalysisEngine, L } from '../analysis-core.mjs';

/* Базовый набор из 33 видимых landmark-точек стоящего человека (y растёт вниз). */
function basePose() {
  const lm = new Array(33);
  for (let i = 0; i < 33; i++) lm[i] = { x: 0.5, y: 0.9, z: 0, visibility: 1 };
  lm[L.NOSE] = { x: 0.5, y: 0.15, z: 0, visibility: 1 };
  lm[L.L_EAR] = { x: 0.45, y: 0.15, z: 0, visibility: 1 };
  lm[L.R_EAR] = { x: 0.55, y: 0.15, z: 0, visibility: 1 };
  lm[L.L_SH] = { x: 0.40, y: 0.30, z: 0, visibility: 1 };
  lm[L.R_SH] = { x: 0.60, y: 0.30, z: 0, visibility: 1 };
  lm[L.L_EL] = { x: 0.38, y: 0.45, z: 0, visibility: 1 };
  lm[L.R_EL] = { x: 0.60, y: 0.45, z: 0, visibility: 1 };
  lm[L.L_WR] = { x: 0.38, y: 0.55, z: 0, visibility: 0.2 }; // левая рука «спрятана»
  lm[L.R_WR] = { x: 0.60, y: 0.50, z: 0, visibility: 1 };
  lm[L.L_HIP] = { x: 0.42, y: 0.55, z: 0, visibility: 1 };
  lm[L.R_HIP] = { x: 0.58, y: 0.55, z: 0, visibility: 1 };
  lm[L.L_KNEE] = { x: 0.42, y: 0.75, z: 0, visibility: 1 };
  lm[L.R_KNEE] = { x: 0.58, y: 0.75, z: 0, visibility: 1 };
  lm[L.L_ANK] = { x: 0.42, y: 0.95, z: 0, visibility: 1 };
  lm[L.R_ANK] = { x: 0.58, y: 0.95, z: 0, visibility: 1 };
  return lm;
}

/* ROI «стол» под линией плеч, где ездит правая кисть. */
const TABLE = { type: 'table', name: 'стол', pts: [[0.45, 0.42], [0.80, 0.42], [0.80, 0.60], [0.45, 0.60]] };

test('протирка стола правой рукой → старт активности и покрытие в финале', () => {
  const eng = new AnalysisEngine({ rois: [TABLE] });
  const events = [];
  let now = 0;
  const step = 33; // ~30 fps

  // ~70 кадров активного протирания: правая кисть пилит по X в зоне стола
  for (let i = 0; i < 70; i++) {
    const lm = basePose();
    const phase = i % 8;
    lm[L.R_WR].x = phase < 4 ? 0.55 + phase * 0.05 : 0.72 - (phase - 4) * 0.05;
    now += step;
    events.push(...eng.analyze(lm, null, now));
  }

  const started = events.find((e) => e.text.startsWith('Начато протирание стола'));
  assert.ok(started, 'должно появиться событие старта протирания стола');
  assert.equal(started.isAct, true);

  // остановка: кисть замерла. Сначала из 42-кадрового окна должны выйти все
  // кадры с махами, потом ещё ≥18 кадров покоя — тогда активность закрывается.
  for (let i = 0; i < 70; i++) {
    const lm = basePose();
    now += step;
    events.push(...eng.analyze(lm, null, now));
  }

  const ended = events.find((e) => /Стол протёрт/.test(e.text));
  assert.ok(ended, 'должно появиться событие завершения с длительностью');
  assert.ok(ended.snapshot, 'финал протирания просит стоп-кадр');

  const cov = events.find((e) => e.coverage && e.coverage.zoneType === 'table');
  assert.ok(cov, 'должно появиться событие покрытия зоны стола');
  assert.ok(cov.coverage.pct > 0, 'покрытие стола должно быть больше нуля, получено: ' + cov.coverage.pct);
});
