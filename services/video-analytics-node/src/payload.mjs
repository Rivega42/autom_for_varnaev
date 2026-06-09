/* Преобразование событий движка analysis-core в события единого журнала.
 *
 * Серверный воркер пишет события в log-service напрямую (он во внутренней сети),
 * в той же форме, что и текущий Python-воркер (см.
 * services/video-analytics/video_analytics/coverage.py и app.py). Так замена
 * Python-детекторов на JS-ядро не ломает контракт `docs/03_API_CONTRACT.md` и
 * существующие дашборды Grafana.
 *
 * Наружу контур отдаёт только СОБЫТИЯ (не сырьё): действия (action_detected) и
 * отчёты о покрытии зон (coverage_report) — симметрично §4 CLAUDE.md.
 */

import { randomUUID } from 'node:crypto';
import { COLORS } from '../../analysis-core/analysis-core.mjs';

/* серьёзность события по цвету из PoC: алерт (падение/SOS) → warning, иначе info */
function severityFor(color) {
  return color === COLORS.alert ? 'warning' : 'info';
}

/* Общий «конверт» события журнала. ts — ВРЕМЯ СОБЫТИЯ (стенные часы), не путать с
 * монотонным временем кадра, которое движок берёт как `now`. */
function envelope({ roomId = null, ts, severity, type }) {
  return {
    id: randomUUID(),
    ts: (ts instanceof Date ? ts : new Date(ts ?? Date.now())).toISOString(),
    source: 'analytics',
    type,
    room_id: roomId,
    severity,
  };
}

/* событие-действие: source=analytics, type=action_detected (origin=server).
 * payload повторяет build_action_event Python-воркера: action/duration_s/hands. */
export function actionEvent(ev, { roomId = null, cameraId = null, ts } = {}) {
  return {
    ...envelope({ roomId, ts, severity: severityFor(ev.color), type: 'action_detected' }),
    message: ev.text,
    payload: {
      origin: 'server',
      ...(ev.action ? { action: ev.action } : {}),
      ...(ev.durationS != null ? { duration_s: ev.durationS } : {}),
      ...(cameraId ? { camera_id: cameraId } : {}),
      ...(ev.snapshot ? { snapshot: true } : {}),
    },
  };
}

/* отчёт о покрытии зоны: type=coverage_report; payload как в build_coverage_event
 * ({zone, zone_id, coverage_pct} — zone_id присутствует ВСЕГДА, как в Python),
 * но сообщение берём из PoC (например «стол протёрт на 85%») — «точь-в-точь как PoC» */
export function coverageEvent(ev, { roomId = null, ts } = {}) {
  const c = ev.coverage;
  return {
    ...envelope({ roomId, ts, severity: 'info', type: 'coverage_report' }),
    message: ev.text,
    payload: {
      zone: c.zoneType,
      zone_id: c.zoneId != null ? c.zoneId : null,
      coverage_pct: c.pct,
    },
  };
}

/* Отобразить событие движка в событие журнала ИЛИ null, если его наружу не шлём.
 * Наружу идут: действия (isAct) и отчёты о покрытии (coverage) — это контракт
 * серверного воркера (см. Python build_action_event/build_coverage_event) и
 * требование показывать покрытие в Grafana. Позы/лампы наружу не уходят. */
export function toJournalEvent(ev, ctx = {}) {
  if (ev.coverage) return coverageEvent(ev, ctx);
  if (ev.isAct) return actionEvent(ev, ctx);
  return null;
}
