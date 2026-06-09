/* Ядро видеоаналитики — единый движок для браузера и сервера (Node).
 *
 * Это дословный перенос логики распознавания из браузерного PoC
 * `services/video-analytics/reference/motion-log.html`. Цель — чтобы в браузере
 * (живой просмотр в настройках камеры) и на сервере (анализ по расписанию / по
 * RTSP / по видеофайлу) работал ОДИН И ТОТ ЖЕ код, а не две похожие реализации.
 *
 * Модуль не зависит ни от DOM, ни от Node-API: на вход — массив landmark-точек
 * MediaPipe PoseLandmarker (нормализованные координаты 0..1) и опциональные
 * world-точки (3D, в метрах), на выход — список событий. Отрисовка скелета,
 * заливка «теплокарты» и снимок-стоп-кадр остаются на стороне хоста (адаптера),
 * но проценты покрытия зон считаются здесь же — чтобы цифры совпадали везде.
 *
 * Координаты: всё внутри ядра — в landmark-координатах (как их отдаёт MediaPipe).
 * Зеркалирование (MIRROR) — чисто визуальная вещь хоста; точки кистей и полигоны
 * зон лежат в одной системе координат, поэтому ядро MIRROR не учитывает.
 */

/* ---------- индексы landmark-точек MediaPipe Pose ---------- */
export const L = {
  NOSE: 0, L_EAR: 7, R_EAR: 8, L_SH: 11, R_SH: 12, L_EL: 13, R_EL: 14,
  L_WR: 15, R_WR: 16, L_HIP: 23, R_HIP: 24, L_KNEE: 25, R_KNEE: 26,
  L_ANK: 27, R_ANK: 28,
};

/* связи скелета (для отрисовки на стороне хоста) */
export const CONN = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28], [15, 17], [15, 19], [15, 21], [16, 18], [16, 20], [16, 22],
  [27, 29], [27, 31], [28, 30], [28, 32], [7, 0], [8, 0],
];

export const COLORS = {
  arm: '#3ef0a0', leg: '#46d6ff', head: '#ffb23e', torso: '#b78bff',
  act: '#ffffff', alert: '#ff5d6c',
};

/* набор детекторов (ключи совпадают с PoC) */
export const DETECTOR_KEYS = [
  'arms', 'legs', 'head', 'torso', 'wipe', 'mop', 'sweep', 'window',
  'wave', 'clap', 'walk', 'presence', 'fall', 'still', 'sos',
];

const ROI_TYPE_RU = { table: 'стол', floor: 'пол', window: 'окно' };
const CLEAN_VERB = { table: 'протёрт', floor: 'вымыт', window: 'вымыто' };
const ACT_TO_ROI = { wipe: 'table', window: 'window', mop: 'floor', sweep: 'floor' };
const ROI_COL = { table: COLORS.arm, floor: COLORS.leg, window: COLORS.torso };

/* ---------- чистые утилиты (дословно из PoC) ---------- */
export const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export const vis = (p) => p && (p.visibility === undefined ? 1 : p.visibility);

export function countReversals(arr, dz) {
  let c = 0, last = 0;
  for (let i = 1; i < arr.length; i++) {
    const d = arr[i] - arr[i - 1];
    if (Math.abs(d) < dz) continue;
    const s = Math.sign(d);
    if (last !== 0 && s !== last) c++;
    last = s;
  }
  return c;
}

export const range = (a) => Math.max(...a) - Math.min(...a);
export const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
export const std = (a) => {
  const m = mean(a);
  return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length);
};
export const inBand = (ys, a, b) => ys.every((v) => v > a && v < b);

/* форма траектории: 'circle' (петля) | 'line' (вдоль одной оси / возвратно-поступательно) */
export function motionShape(xs, ys) {
  const n = xs.length;
  if (n < 6) return 'line';
  const cx = mean(xs), cy = mean(ys);
  let sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - cx, dy = ys[i] - cy;
    sxx += dx * dx; syy += dy * dy; sxy += dx * dy;
  }
  sxx /= n; syy /= n; sxy /= n;
  const tr = sxx + syy, disc = Math.sqrt(Math.max(0, (tr * tr) / 4 - (sxx * syy - sxy * sxy)));
  const l1 = tr / 2 + disc, l2 = tr / 2 - disc, aspect = l1 > 1e-9 ? l2 / l1 : 0;
  let prev = null, net = 0, abs = 0;
  for (let i = 0; i < n; i++) {
    const a = Math.atan2(ys[i] - cy, xs[i] - cx);
    if (prev !== null) {
      let d = a - prev;
      while (d > Math.PI) d -= 2 * Math.PI;
      while (d < -Math.PI) d += 2 * Math.PI;
      net += d; abs += Math.abs(d);
    }
    prev = a;
  }
  const circ = abs > 1e-3 ? Math.abs(net) / abs : 0;
  return (aspect > 0.4 && circ > 0.55 && Math.abs(net) > Math.PI) ? 'circle' : 'line';
}

export const shapeText = (s) => (s === 'circle' ? 'по кругу' : s === 'mixed' ? 'разнонаправленно' : 'вперёд-назад');
export const clamp01 = (v) => Math.max(0, Math.min(1, v));
export const r4 = (v) => Math.round((v == null ? 0 : v) * 1e4) / 1e4;
export function packLM(a) {
  return a ? a.map((p) => [r4(p.x), r4(p.y), r4(p.z), r4(p.visibility == null ? 1 : p.visibility)]) : null;
}

/* угол в точке b между b->a и b->c (3D, в градусах) */
export function angleAt(a, b, c) {
  const v1 = [a.x - b.x, a.y - b.y, a.z - b.z], v2 = [c.x - b.x, c.y - b.y, c.z - b.z];
  const d = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2], m1 = Math.hypot(...v1), m2 = Math.hypot(...v2);
  return (m1 && m2) ? (Math.acos(Math.max(-1, Math.min(1, d / (m1 * m2)))) * 180) / Math.PI : 180;
}

/* точка в многоугольнике (ray casting), pts = [[x,y]*4] в landmark-координатах */
export function pip(px, py, pts) {
  let c = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
    if (((yi > py) !== (yj > py)) && (px < ((xj - xi) * (py - yi)) / (yj - yi) + xi)) c = !c;
  }
  return c;
}

/* точка покраски = проекция на кисть/тряпку: продлеваем «локоть→запястье» за запястье */
export const handPoint = (lm, wr) => {
  const w = lm[wr], e = lm[wr === 16 ? 14 : 13] || w;
  return { x: w.x + (w.x - e.x) * 0.45, y: w.y + (w.y - e.y) * 0.45 };
};

/* ---------- накопитель «протёртости» зон (замена heat-канваса) ----------
 * Сетка sw×sh в landmark-координатах; кисти «закрашивают» ячейки в радиусе.
 * coverageByZone() считает долю закрашенных ячеек внутри каждого полигона зоны —
 * это серверный аналог попиксельного coverageByZone() из PoC. */
export class HeatGrid {
  constructor(sw = 200, aspect = 16 / 9) {
    this.sw = sw;
    this.sh = Math.max(1, Math.round(sw / aspect));
    this.cells = new Uint8Array(this.sw * this.sh);
  }

  clear() {
    this.cells.fill(0);
  }

  /* закрасить диск радиуса r (в нормированных landmark-единицах по X) вокруг точки */
  stamp(x, y, r) {
    const { sw, sh } = this;
    const rad = Math.max(0.02, r);
    const x0 = Math.max(0, Math.floor((x - rad) * sw)), x1 = Math.min(sw - 1, Math.ceil((x + rad) * sw));
    const y0 = Math.max(0, Math.floor((y - rad) * sw)), y1 = Math.min(sh - 1, Math.ceil((y + rad) * sw));
    for (let py = y0; py <= y1; py++) {
      for (let px = x0; px <= x1; px++) {
        const lx = (px + 0.5) / sw, ly = (py + 0.5) / sw;
        if (Math.hypot(lx - x, ly - y) <= rad) this.cells[py * sw + px] = 1;
      }
    }
  }

  /* доля закрашенных ячеек внутри полигона pts (0..100) */
  coverage(pts) {
    const { sw, sh, cells } = this;
    let inside = 0, painted = 0;
    for (let py = 0; py < sh; py++) {
      for (let px = 0; px < sw; px++) {
        const lx = (px + 0.5) / sw, ny = (py + 0.5) / sw;
        if (pip(lx, ny, pts)) {
          inside++;
          if (cells[py * sw + px]) painted++;
        }
      }
    }
    return inside ? Math.round((100 * painted) / inside) : 0;
  }
}

/* ---------- движок ----------
 * Хранит всё состояние разбора (как модульные переменные PoC) и на каждый кадр
 * выдаёт список событий. Событие: {text, color, isAct, snapshot, coverage?}.
 *   text     — человекочитаемое сообщение (рус.), как в PoC log();
 *   color    — цвет (для UI/лога);
 *   isAct    — это «активность» (старт/конец уборки, действие) — копия флага log();
 *   snapshot — true, если PoC просил стоп-кадр (snapshot()); хост сделает кадр сам;
 *   coverage — для финального события зоны: {zoneType, zoneName, pct}.
 */
export class AnalysisEngine {
  constructor(opts = {}) {
    this.enabled = {};
    for (const k of DETECTOR_KEYS) this.enabled[k] = opts.enabled ? !!opts.enabled[k] : true;
    this.SENS = opts.sens ?? 1;
    /* зоны: [{type:'table'|'floor'|'window', pts:[[x,y]*4], name?}] */
    this.rois = (opts.rois ?? []).map((r) => ({ ...r, cov: 0 }));
    this.heat = new HeatGrid(opts.gridWidth ?? 200, opts.aspect ?? 16 / 9);

    /* состояния (дословно из PoC) */
    this.armZone = { left: 'rest', right: 'rest' };
    this.armCand = { left: { z: 'rest', n: 0 }, right: { z: 'rest', n: 0 } };
    this.bothUp = false;
    this.kneeUp = { left: false, right: false };
    this.headDir = 'center';
    this.headCand = { d: 'center', n: 0 };
    this.crouch = false;
    this.lean = 'none';
    this.hist = [];
    this.WIN = 42;
    this.actState = { mop: false, sweep: false, wipe: false, window: false, wave: false, walk: false };
    this.actStart = {};
    this.onF = {};
    this.offF = {};
    this.lastClap = 0;
    this.clapArmed = true;
    this.walkSeq = [];
    this.cleanLabel = '';
    this.prevKey = {};
    this.motionEMA = 0;
    this.lastMoveT = 0;
    this.stillFlagged = false;
    this.fallCD = 0;
    this.sosCD = 0;
    this.lastTorso = 0.25;
    this.cleanColor = COLORS.arm;
    this.cleanHandIdx = [];
    this.cleanClip = null;
    this.cleanZonesHit = new Set();
    this.handPrev = {};

    /* буфер событий текущего кадра */
    this._events = [];
  }

  /* аналог log(): в браузере хост дополнительно рисует/постит; здесь — копим */
  _log(text, color, isAct = false, snapshot = false, extra = null) {
    this._events.push({ text, color, isAct: !!isAct, snapshot: !!snapshot, ...(extra || {}) });
  }

  /* zone lookup как roiObjAt из PoC */
  _roiObjAt(x, y) {
    for (const r of this.rois) if (pip(x, y, r.pts)) return r;
    return null;
  }

  /* основной разбор кадра. now — миллисекунды (аналог performance.now()) */
  analyze(lm, world, now) {
    this._events = [];
    const k = this.SENS;
    const g = (i) => lm[i];
    const shMidY = (g(L.L_SH).y + g(L.R_SH).y) / 2, shMidX = (g(L.L_SH).x + g(L.R_SH).x) / 2;
    const shW = Math.max(0.05, dist(g(L.L_SH), g(L.R_SH)));
    const hipMidY = (g(L.L_HIP).y + g(L.R_HIP).y) / 2, torso = Math.max(0.08, Math.abs(hipMidY - shMidY));
    const noseY = g(L.NOSE).y;
    this.lastTorso = torso;

    if (this.enabled.arms) {
      [['left', L.L_WR, L.L_SH, 'левая'], ['right', L.R_WR, L.R_SH, 'правая']].forEach(([side, wi, si, word]) => {
        const wr = g(wi), sh = g(si);
        let z = 'rest';
        if (vis(wr) > 0.5) {
          const om = 0.02 / k, um = 0.03 / k;
          if (wr.y < noseY - om) z = 'over';
          else if (wr.y < shMidY - um) z = 'up';
          else if (Math.abs(wr.x - sh.x) > (shW * 1.05) / k && wr.y < shMidY + 0.10) z = 'side';
          else z = 'rest';
        }
        const cd = this.armCand[side];
        if (z === cd.z) cd.n++;
        else { cd.z = z; cd.n = 1; }
        if (cd.n >= 3 && z !== this.armZone[side]) {
          const prev = this.armZone[side];
          this.armZone[side] = z;
          if (z === 'rest') { if (prev !== 'rest') this._log('Опущена ' + word + ' рука', COLORS.arm); }
          else {
            const w = { over: 'над головой', up: 'вверх', side: 'в сторону' }[z];
            this._log('Поднята ' + word + ' рука — ' + w, COLORS.arm);
          }
        }
      });
      const bu = this.armZone.left !== 'rest' && this.armZone.right !== 'rest'
        && this.armZone.left !== 'side' && this.armZone.right !== 'side';
      if (bu && !this.bothUp) { this.bothUp = true; this._log('Подняты обе руки', COLORS.arm); }
      if (!bu && this.bothUp) this.bothUp = false;
    }

    if (this.enabled.legs) {
      [['left', L.L_KNEE, 'левое'], ['right', L.R_KNEE, 'правое']].forEach(([side, ki, word]) => {
        const kn = g(ki);
        let up = false;
        if (vis(kn) > 0.5) up = kn.y < hipMidY + torso * (0.55 / k);
        if (up && !this.kneeUp[side]) {
          this.kneeUp[side] = true;
          this._log('Поднято ' + word + ' колено', COLORS.leg);
          this.walkSeq.push({ side, t: now });
          if (this.walkSeq.length > 6) this.walkSeq.shift();
        }
        if (!up) this.kneeUp[side] = false;
      });
    }

    if (this.enabled.head) {
      const le = vis(g(L.L_EAR)), re = vis(g(L.R_EAR)), off = (g(L.NOSE).x - shMidX) / shW;
      let d = 'center';
      if (re < 0.4 && le > 0.5) d = 'right';
      else if (le < 0.4 && re > 0.5) d = 'left';
      else if (off > 0.22 / k) d = 'right';
      else if (off < -0.22 / k) d = 'left';
      if (d === this.headCand.d) this.headCand.n++;
      else { this.headCand.d = d; this.headCand.n = 1; }
      if (this.headCand.n >= 4 && d !== this.headDir) {
        this.headDir = d;
        if (d === 'center') this._log('Голова — прямо', COLORS.head);
        else this._log('Голова повёрнута ' + (d === 'left' ? 'влево' : 'вправо'), COLORS.head);
      }
    }

    if (this.enabled.torso) {
      const W = world, vok = (i) => vis(g(i)) > 0.5;
      let cr = false, ln = 'none', known = false;
      if (W) {
        const ang = [];
        if (vok(L.L_HIP) && vok(L.L_KNEE) && vok(L.L_ANK)) ang.push(angleAt(W[L.L_HIP], W[L.L_KNEE], W[L.L_ANK]));
        if (vok(L.R_HIP) && vok(L.R_KNEE) && vok(L.R_ANK)) ang.push(angleAt(W[L.R_HIP], W[L.R_KNEE], W[L.R_ANK]));
        if (ang.length) { known = true; cr = Math.min(...ang) < 115; }
        if (vok(L.L_SH) && vok(L.R_SH) && vok(L.L_HIP) && vok(L.R_HIP)) {
          const sx = (W[L.L_SH].x + W[L.R_SH].x) / 2, sy = (W[L.L_SH].y + W[L.R_SH].y) / 2;
          const hx = (W[L.L_HIP].x + W[L.R_HIP].x) / 2, hy = (W[L.L_HIP].y + W[L.R_HIP].y) / 2;
          const lat = Math.abs(sy - hy) > 1e-3 ? (sx - hx) / Math.abs(sy - hy) : 0;
          if (lat > 0.35 / k) ln = 'right';
          else if (lat < -0.35 / k) ln = 'left';
        }
      }
      if (known) {
        if (cr && !this.crouch) { this.crouch = true; this._log('Приседание', COLORS.torso); }
        if (!cr && this.crouch) { this.crouch = false; this._log('Подъём из приседа', COLORS.torso); }
      }
      if (ln !== this.lean && ln !== 'none') this._log('Наклон корпуса ' + (ln === 'left' ? 'влево' : 'вправо'), COLORS.torso);
      this.lean = ln;
    }

    if (this.enabled.still) {
      const ks = [L.NOSE, L.L_WR, L.R_WR, L.L_SH, L.R_SH, L.L_ANK, L.R_ANK];
      let m = 0, c = 0;
      ks.forEach((i) => {
        const p = lm[i];
        if (this.prevKey[i]) { m += Math.hypot(p.x - this.prevKey[i].x, p.y - this.prevKey[i].y); c++; }
        this.prevKey[i] = { x: p.x, y: p.y };
      });
      this.motionEMA = this.motionEMA * 0.8 + (c ? m / c : 0) * 0.2;
      if (this.motionEMA > 0.004) {
        if (this.stillFlagged) { this.stillFlagged = false; this._log('Движение возобновилось', COLORS.head); }
        this.lastMoveT = now;
      } else if (!this.stillFlagged && this.lastMoveT && now - this.lastMoveT > 6000) {
        this.stillFlagged = true;
        this._log('Нет движения более 6 с', COLORS.head);
      }
    }

    const fr = {
      t: now, lwx: g(L.L_WR).x, lwy: g(L.L_WR).y, rwx: g(L.R_WR).x, rwy: g(L.R_WR).y,
      lwv: vis(g(L.L_WR)), rwv: vis(g(L.R_WR)), ny: noseY, shMidY, hipMidY, torso, wd: dist(g(L.L_WR), g(L.R_WR)),
    };
    this.hist.push(fr);
    if (this.hist.length > this.WIN) this.hist.shift();
    if (this.hist.length >= this.WIN - 2) this._detectActivities(lm, now);

    return this._events;
  }

  _startMsg(t) {
    return t === 'mop' ? 'Начато мытьё пола шваброй…'
      : t === 'sweep' ? 'Начато подметание…'
      : t === 'wipe' ? 'Начато протирание стола (' + this.cleanLabel + ')…'
      : 'Начато протирание окна (' + this.cleanLabel + ')…';
  }

  _endMsg(t, sec) {
    return t === 'mop' ? 'Пол вымыт (шваброй, ' + sec + ' с)'
      : t === 'sweep' ? 'Подметание завершено (' + sec + ' с)'
      : t === 'wipe' ? 'Стол протёрт (' + this.cleanLabel + ', ' + sec + ' с)'
      : 'Окно протёрто (' + this.cleanLabel + ', ' + sec + ' с)';
  }

  /* стейт-машина старт/конец активности (дословно transition() из PoC) */
  _transition(key, active, onStart, onEnd, now) {
    this.onF[key] = this.onF[key] || 0;
    this.offF[key] = this.offF[key] || 0;
    if (active) { this.onF[key]++; this.offF[key] = 0; } else { this.offF[key]++; this.onF[key] = 0; }
    if (!this.actState[key] && this.onF[key] >= 6) {
      this.actState[key] = true; this.actStart[key] = now; onStart();
    }
    if (this.actState[key] && this.offF[key] >= 18) {
      this.actState[key] = false; onEnd(((now - this.actStart[key]) / 1000).toFixed(1));
    }
  }

  /* закрасить рабочие кисти текущего кадра (для покрытия зоны), обрезая по зоне */
  _paintHands(lm) {
    const idx = this.cleanHandIdx && this.cleanHandIdx.length ? this.cleanHandIdx : [];
    if (!idx.length) return;
    idx.forEach((wr) => {
      const pt = handPoint(lm, wr);
      // красим только если попадает в зону уборки (аналог clip по cleanClip)
      const inClip = !this.cleanClip || this.cleanClip.some((poly) => pip(pt.x, pt.y, poly));
      if (inClip) this.heat.stamp(pt.x, pt.y, this.lastTorso * 0.62);
      this.handPrev[wr] = pt;
    });
  }

  _coverageByZone() {
    for (const r of this.rois) r.cov = this.heat.coverage(r.pts);
  }

  _detectActivities(lm, now) {
    const h = this.hist, k = this.SENS, last = h[h.length - 1];
    const lwx = h.map((f) => f.lwx), lwy = h.map((f) => f.lwy), rwx = h.map((f) => f.rwx), rwy = h.map((f) => f.rwy);
    const shMidY = last.shMidY, hipMidY = last.hipMidY, noseY = last.ny;
    const dz = 0.004 / k, lRev = countReversals(lwx, dz), rRev = countReversals(rwx, dz);
    let anyAct = false;

    /* ---------- семейство УБОРКИ ---------- */
    const visBoth = h.every((f) => f.lwv > 0.4 && f.rwv > 0.4);
    const wdArr = h.map((f) => f.wd);
    const mx = h.map((f) => (f.lwx + f.rwx) / 2), my = h.map((f) => (f.lwy + f.rwy) / 2);
    const midRevX = countReversals(mx, dz), midRevY = countReversals(my, dz);
    const rigid = visBoth && std(wdArr) < 0.035 * k && range(wdArr) < 0.07;
    const implement = rigid && Math.max(range(mx), range(my)) > 0.06 / k && Math.max(midRevX, midRevY) >= 3;
    const lowZone = mean(my) > (shMidY + hipMidY) / 2;

    const visFrac = (arr) => arr.filter((v) => v > 0.3).length / arr.length;
    const Lh = { vis: visFrac(h.map((f) => f.lwv)) >= 0.6, xr: lRev, yr: countReversals(lwy, dz), rx: range(lwx), ry: range(lwy), shape: motionShape(lwx, lwy), my: mean(lwy) };
    const Rh = { vis: visFrac(h.map((f) => f.rwv)) >= 0.6, xr: rRev, yr: countReversals(rwy, dz), rx: range(rwx), ry: range(rwy), shape: motionShape(rwx, rwy), my: mean(rwy) };

    let activeType = null, pts = [], hidx = [], clipType = null, cleanZoneNow = null;
    if (this.rois.length) {
      const consider = (x, y, Hh, name) => {
        if (!(Hh.vis && (Hh.xr >= 3 || Hh.yr >= 3 || Hh.shape === 'circle'))) return null;
        const z = this._roiObjAt(x, y);
        return z ? { zone: z, name, shape: Hh.shape, rx: Hh.rx, ry: Hh.ry, x, y } : null;
      };
      const hs = [consider(last.lwx, last.lwy, Lh, 'левой рукой'), consider(last.rwx, last.rwy, Rh, 'правой рукой')].filter(Boolean);
      if (hs.length) {
        const cnt = new Map();
        hs.forEach((o) => cnt.set(o.zone, (cnt.get(o.zone) || 0) + 1));
        let zone = hs[0].zone, best = -1;
        cnt.forEach((c, z) => { if (c > best) { best = c; zone = z; } });
        const sel = hs.filter((o) => o.zone === zone);
        pts = sel.map((o) => ({ x: o.x, y: o.y }));
        hidx = sel.map((o) => (o.name === 'левой рукой' ? 15 : 16));
        clipType = zone.type;
        cleanZoneNow = zone;
        const rt = zone.type;
        if (rt === 'table') activeType = 'wipe';
        else if (rt === 'window') activeType = 'window';
        else activeType = sel.some((o) => o.rx >= o.ry) ? 'sweep' : 'mop';
        if (activeType === 'wipe' || activeType === 'window') {
          const handsTxt = sel.length > 1 ? 'двумя руками' : sel[0].name;
          const shp = sel.length > 1 ? (sel[0].shape === sel[1].shape ? sel[0].shape : 'mixed') : sel[0].shape;
          this.cleanLabel = handsTxt + ', ' + shapeText(shp);
        }
      }
    } else if (implement && lowZone) {
      activeType = range(mx) >= range(my) * 1.1 ? 'sweep' : 'mop';
      pts = [{ x: last.lwx, y: last.lwy }, { x: last.rwx, y: last.rwy }];
      hidx = [15, 16];
    } else {
      const upTop = noseY - 0.10, upLow = shMidY + 0.05;
      const Lwin = Lh.vis && inBand(lwy, upTop, upLow) && (Lh.yr >= 3 || Lh.shape === 'circle') && Lh.ry > 0.05;
      const Rwin = Rh.vis && inBand(rwy, upTop, upLow) && (Rh.yr >= 3 || Rh.shape === 'circle') && Rh.ry > 0.05;
      const Ltab = Lh.vis && mean(lwy) > shMidY && (Lh.xr >= 3 || Lh.shape === 'circle') && (Lh.rx > 0.05 || Lh.shape === 'circle');
      const Rtab = Rh.vis && mean(rwy) > shMidY && (Rh.xr >= 3 || Rh.shape === 'circle') && (Rh.rx > 0.05 || Rh.shape === 'circle');
      if (Ltab || Rtab) {
        activeType = 'wipe';
        const hands = (Ltab && Rtab) ? 'двумя руками' : Ltab ? 'левой рукой' : 'правой рукой';
        const shp = (Ltab && Rtab) ? (Lh.shape === Rh.shape ? Lh.shape : 'mixed') : (Ltab ? Lh.shape : Rh.shape);
        this.cleanLabel = hands + ', ' + shapeText(shp);
        if (Ltab) { pts.push({ x: last.lwx, y: last.lwy }); hidx.push(15); }
        if (Rtab) { pts.push({ x: last.rwx, y: last.rwy }); hidx.push(16); }
      } else if (Lwin || Rwin) {
        activeType = 'window';
        const hands = (Lwin && Rwin) ? 'двумя руками' : Lwin ? 'левой рукой' : 'правой рукой';
        const shp = (Lwin && Rwin) ? (Lh.shape === Rh.shape ? Lh.shape : 'mixed') : (Lwin ? Lh.shape : Rh.shape);
        this.cleanLabel = hands + ', ' + shapeText(shp);
        if (Lwin) { pts.push({ x: last.lwx, y: last.lwy }); hidx.push(15); }
        if (Rwin) { pts.push({ x: last.rwx, y: last.rwy }); hidx.push(16); }
      }
    }
    if (activeType && !this.enabled[activeType]) activeType = null;
    const palette = { mop: COLORS.leg, sweep: COLORS.head, wipe: COLORS.arm, window: COLORS.torso };
    if (activeType) {
      this.cleanColor = palette[activeType];
      anyAct = true;
      this.cleanHandIdx = hidx;
      this.cleanClip = (this.rois.length && clipType) ? this.rois.filter((r) => r.type === clipType).map((r) => r.pts) : null;
      if (cleanZoneNow) this.cleanZonesHit.add(cleanZoneNow);
      this._paintHands(lm); // копим покрытие каждый активный кадр
    }
    ['mop', 'sweep', 'wipe', 'window'].forEach((t) => {
      this._transition(t, activeType === t,
        () => { this._log(this._startMsg(t), COLORS.act, true); this.cleanZonesHit.clear(); },
        (sec) => {
          this._log(this._endMsg(t, sec), COLORS.act, true, true);
          this._coverageByZone();
          const rt = ACT_TO_ROI[t];
          [...this.cleanZonesHit].filter((z) => z.type === rt).forEach((z) => {
            const name = z.name || ROI_TYPE_RU[z.type];
            this._log(name + ' ' + CLEAN_VERB[z.type] + ' на ' + (z.cov || 0) + '%', ROI_COL[z.type], false, false,
              { coverage: { zoneType: z.type, zoneName: name, pct: z.cov || 0 } });
            this.cleanZonesHit.delete(z);
          });
        }, now);
    });

    /* ---------- прочие действия ---------- */
    if (this.enabled.wave) {
      const lUp = h.every((f) => f.lwy < f.shMidY) && lRev >= 3 && range(lwx) > 0.04;
      const rUp = h.every((f) => f.rwy < f.shMidY) && rRev >= 3 && range(rwx) > 0.04;
      const waving = lUp || rUp;
      this._transition('wave', waving, () => this._log('Машет рукой', COLORS.act, true),
        (sec) => this._log('Помахивание завершено (' + sec + ' с)', COLORS.act, true), now);
      if (waving) anyAct = true;
    }

    if (this.enabled.clap) {
      const near = last.wd < 0.07 * k, frontY = last.lwy < last.hipMidY && last.rwy < last.hipMidY;
      if (near && this.clapArmed && frontY && now - this.lastClap > 250) {
        this._log('Хлопок в ладоши', COLORS.act, true);
        this.lastClap = now; this.clapArmed = false; anyAct = true;
      }
      if (last.wd > 0.13 * k) this.clapArmed = true;
    }

    if (this.enabled.walk) {
      const recent = this.walkSeq.filter((s) => now - s.t < 2500);
      let alt = 0;
      for (let i = 1; i < recent.length; i++) if (recent[i].side !== recent[i - 1].side) alt++;
      const walking = alt >= 2;
      this._transition('walk', walking, () => this._log('Ходьба на месте', COLORS.act, true),
        (sec) => this._log('Остановился (ходьба ' + sec + ' с)', COLORS.act, true), now);
      if (walking) anyAct = true;
    }

    /* ---------- мониторинг ---------- */
    if (this.enabled.fall) {
      const drop = last.shMidY - h[0].shMidY, torsoVert = Math.abs(last.hipMidY - last.shMidY);
      const horizontal = torsoVert < 0.12 || last.ny > last.hipMidY;
      if (drop > 0.22 / k && horizontal && now - this.fallCD > 5000) {
        this.fallCD = now;
        this._log('⚠ Возможное падение', COLORS.alert, true, true);
      }
    }

    if (this.enabled.sos) {
      const overhead = h.every((f) => f.lwy < f.ny && f.rwy < f.ny), waving = lRev >= 3 && rRev >= 3;
      if (overhead && waving && now - this.sosCD > 4000) {
        this.sosCD = now;
        this._log('⚠ Сигнал бедствия (обе руки над головой)', COLORS.alert, true, true);
      }
    }

    return anyAct;
  }
}
