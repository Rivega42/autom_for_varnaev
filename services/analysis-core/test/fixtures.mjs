/* Общие тест-фикстуры для движка и серверного конвейера.
 * Один и тот же синтетический сценарий «протирки стола» проверяет, что браузер
 * (движок) и сервер (конвейер) ведут себя одинаково — поэтому фикстура одна. */
import { L } from '../analysis-core.mjs';

/* Базовый набор из 33 видимых landmark-точек стоящего человека (y растёт вниз). */
export function basePose() {
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
export const TABLE = {
  type: 'table', name: 'стол', zoneId: 7,
  pts: [[0.45, 0.42], [0.80, 0.42], [0.80, 0.60], [0.45, 0.60]],
};

/* Кадры протирки: ~70 кадров правая кисть пилит по X в зоне стола, затем ~70
 * кадров покоя (чтобы из 42-кадрового окна вышли все махи и активность закрылась).
 * Возвращает массив {lm, world, ts}. */
export function wipingFrames() {
  const frames = [];
  let ts = 0;
  const step = 33; // ~30 fps
  for (let i = 0; i < 70; i++) {
    const lm = basePose();
    const phase = i % 8;
    lm[L.R_WR].x = phase < 4 ? 0.55 + phase * 0.05 : 0.72 - (phase - 4) * 0.05;
    ts += step;
    frames.push({ lm, world: null, ts });
  }
  for (let i = 0; i < 70; i++) {
    ts += step;
    frames.push({ lm: basePose(), world: null, ts });
  }
  return frames;
}
