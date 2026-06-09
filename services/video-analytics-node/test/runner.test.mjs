/* Тесты серверного конвейера: те же синтетические кадры «протирки стола»,
 * что и в тесте движка, должны на сервере дать события журнала в КОНТРАКТНОЙ
 * форме (action_detected + coverage_report), совпадающей с Python-воркером. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { AnalysisEngine } from '../../analysis-core/analysis-core.mjs';
import { TABLE, wipingFrames } from '../../analysis-core/test/fixtures.mjs';
import { runAnalysis } from '../src/runner.mjs';
import { arrayFrames } from '../src/sources.mjs';
import { toJournalEvent, actionEvent, coverageEvent } from '../src/payload.mjs';

test('runAnalysis: протирка стола → события журнала в контрактной форме', async () => {
  const engine = new AnalysisEngine({ rois: [TABLE] });
  const sink = [];
  const summary = await runAnalysis({
    frames: arrayFrames(wipingFrames()),
    engine,
    sink: async (e) => sink.push(e),
    roomId: 'room-1',
    cameraId: 'cam-9',
  });

  assert.equal(summary.framesProcessed, 140);
  assert.ok(summary.emitted > 0);

  // все события — analytics, с валидными типами и реальным (не 1970) временем
  for (const e of sink) {
    assert.equal(e.source, 'analytics');
    assert.ok(['action_detected', 'coverage_report'].includes(e.type));
    assert.ok(typeof e.id === 'string' && e.id.length >= 36);
    assert.ok(typeof e.ts === 'string');
    assert.ok(new Date(e.ts).getFullYear() >= 2020, 'ts должен быть стенным временем, а не 1970');
    assert.equal(e.room_id, 'room-1');
    assert.ok(e.message);
  }

  const started = sink.find((e) => e.type === 'action_detected' && e.message.startsWith('Начато протирание стола'));
  assert.ok(started, 'должно быть action_detected о старте протирания');
  assert.equal(started.payload.origin, 'server');
  assert.equal(started.payload.camera_id, 'cam-9');
  assert.equal(started.payload.action, 'wipe');

  const ended = sink.find((e) => e.type === 'action_detected' && /Стол протёрт/.test(e.message));
  assert.ok(ended, 'должно быть action_detected о завершении');
  assert.equal(ended.payload.duration_s > 0, true);

  const cov = sink.find((e) => e.type === 'coverage_report');
  assert.ok(cov, 'должен быть coverage_report');
  assert.equal(cov.payload.zone, 'table');
  assert.equal(cov.payload.zone_id, 7);
  assert.ok(cov.payload.coverage_pct > 0);
  assert.match(cov.message, /стол протёрт на \d+%/);
});

test('toJournalEvent: позы наружу не уходят, действия и покрытия — да', () => {
  // обычная поза (не действие, без покрытия) → null
  assert.equal(toJournalEvent({ text: 'Поднята левая рука', color: '#3ef0a0', isAct: false }), null);
  // действие → action_detected
  const a = toJournalEvent({ text: 'Машет рукой', color: '#ffffff', isAct: true, action: 'wave' }, { roomId: 'r', cameraId: 'c' });
  assert.equal(a.type, 'action_detected');
  assert.equal(a.payload.action, 'wave');
  // покрытие → coverage_report
  const c = toJournalEvent({ text: 'стол протёрт на 50%', color: '#3ef0a0', isAct: false, coverage: { zoneType: 'table', zoneId: 3, pct: 50 } });
  assert.equal(c.type, 'coverage_report');
  assert.equal(c.payload.coverage_pct, 50);
});

test('actionEvent: алерт (падение/SOS) → severity=warning', () => {
  const ev = actionEvent({ text: '⚠ Возможное падение', color: '#ff5d6c', isAct: true, snapshot: true, action: 'fall' });
  assert.equal(ev.severity, 'warning');
  assert.equal(ev.payload.snapshot, true);
  assert.equal(ev.payload.action, 'fall');
});

test('coverageEvent: zone_id присутствует всегда (как в build_coverage_event)', () => {
  // с известным zoneId
  const e = coverageEvent({ text: 'окно протёрто на 80%', coverage: { zoneType: 'window', zoneId: 2, pct: 80 } }, { roomId: 'r2' });
  assert.deepEqual(e.payload, { zone: 'window', zone_id: 2, coverage_pct: 80 });
  // без zoneId → ключ всё равно есть, со значением null
  const e2 = coverageEvent({ text: 'стол протёрт на 10%', coverage: { zoneType: 'table', pct: 10 } });
  assert.equal(e2.payload.zone_id, null);
  assert.equal(e2.type, 'coverage_report');
});
