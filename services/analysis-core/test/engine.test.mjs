/* Дымовой тест движка: синтетическая «протирка стола» правой рукой должна дать
 * событие «Начато протирание стола…», а после остановки — финал с покрытием зоны.
 * Так мы проверяем, что перенесённая из PoC стейт-машина и расчёт покрытия живые. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { AnalysisEngine } from '../analysis-core.mjs';
import { TABLE, wipingFrames } from './fixtures.mjs';

test('протирка стола правой рукой → старт активности и покрытие в финале', () => {
  const eng = new AnalysisEngine({ rois: [TABLE] });
  const events = [];
  for (const f of wipingFrames()) events.push(...eng.analyze(f.lm, f.world, f.ts));

  const started = events.find((e) => e.text.startsWith('Начато протирание стола'));
  assert.ok(started, 'должно появиться событие старта протирания стола');
  assert.equal(started.isAct, true);
  assert.equal(started.action, 'wipe');

  const ended = events.find((e) => /Стол протёрт/.test(e.text));
  assert.ok(ended, 'должно появиться событие завершения с длительностью');
  assert.ok(ended.snapshot, 'финал протирания просит стоп-кадр');
  assert.equal(ended.action, 'wipe');
  assert.ok(ended.durationS > 0, 'у завершения должна быть длительность');

  const cov = events.find((e) => e.coverage && e.coverage.zoneType === 'table');
  assert.ok(cov, 'должно появиться событие покрытия зоны стола');
  assert.equal(cov.coverage.zoneId, 7);
  assert.ok(cov.coverage.pct > 0, 'покрытие стола должно быть больше нуля, получено: ' + cov.coverage.pct);
});

test('частичная карта enabled выключает только явные false', () => {
  const eng = new AnalysisEngine({ enabled: { wave: false } });
  assert.equal(eng.enabled.wave, false);
  assert.equal(eng.enabled.arms, true, 'неупомянутые детекторы остаются включёнными');
  assert.equal(eng.enabled.wipe, true);
});

test('зона, удалённая во время уборки, не даёт фантомного отчёта о покрытии', () => {
  const eng = new AnalysisEngine({ rois: [TABLE] });
  const frames = wipingFrames();
  const events = [];
  // активная фаза — уборка подтверждается и зона попадает в cleanZonesHit
  for (const f of frames.slice(0, 70)) events.push(...eng.analyze(f.lm, f.world, f.ts));
  assert.ok(events.some((e) => e.text.startsWith('Начато протирание стола')));
  // оператор удалил все зоны до завершения уборки
  eng.rois = [];
  for (const f of frames.slice(70)) events.push(...eng.analyze(f.lm, f.world, f.ts));
  assert.ok(events.some((e) => /Стол протёрт/.test(e.text)), 'завершение уборки фиксируется');
  assert.equal(events.find((e) => e.coverage), undefined, 'отчёта по удалённой зоне нет');
});
