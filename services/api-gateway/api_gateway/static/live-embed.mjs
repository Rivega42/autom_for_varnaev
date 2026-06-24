/* Нативный «Живой анализ» прямо в карточке камеры (без iframe).
 *
 * Это компактный встраиваемый компонент: берёт MJPEG-поток камеры и ROI-зоны из
 * БД, гоняет ЕДИНОЕ ядро analysis-core (то же, что и сервер), рисует скелет и
 * заливку «протёртости», ведёт журнал и шлёт события (+стоп-кадр) в контур.
 *
 * Распознавание целиком в ядре — здесь только хост: видео-элемент, отрисовка,
 * визуальная heat-заливка, стоп-кадр. Координаты — landmark (0..1), без зеркала
 * (IP-камеру не отражаем): скелет и зоны совпадают с видео один-в-один.
 */

import { PoseLandmarker, FilesetResolver } from "./vendor/mediapipe/vision_bundle.mjs";
import { AnalysisEngine, CONN, vis, handPoint } from "./analysis-core.mjs";

let _landmarker = null; // модель грузим один раз на страницу

async function initModel() {
  if (_landmarker) return _landmarker;
  const fileset = await FilesetResolver.forVisionTasks("vendor/mediapipe/wasm");
  _landmarker = await PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: "vendor/model/pose_landmarker.task", delegate: "GPU" },
    runningMode: "VIDEO", numPoses: 1,
    minPoseDetectionConfidence: 0.5, minTrackingConfidence: 0.5, minPosePresenceConfidence: 0.5,
  });
  return _landmarker;
}

/* Русские имена типов зон (подписи, журнал). */
const RU_ZONE = { table: "стол", floor: "пол", window: "окно" };
const zoneLabel = (z) => z.note || RU_ZONE[z.zone_type] || z.zone_type;

/* зоны БД (zone_type/polygon/id) → ROI ядра (type/pts/name/zoneId) */
function zonesToRois(zones) {
  return (zones || []).map((z) => ({
    type: z.zone_type, pts: z.polygon, zoneId: z.id, name: zoneLabel(z), cov: 0,
  }));
}

/* сглаживание landmark между кадрами (как в PoC: экспоненциальное, SM=0.5) */
function makeSmoother() {
  let s = null;
  return (lm) => {
    if (!s) { s = lm.map((p) => ({ ...p })); return s; }
    for (let i = 0; i < lm.length; i++) {
      s[i].x += (lm[i].x - s[i].x) * 0.5; s[i].y += (lm[i].y - s[i].y) * 0.5;
      s[i].z = lm[i].z; s[i].visibility = lm[i].visibility;
    }
    return s;
  };
}

/* Смонтировать живой анализ в container. Возвращает { stop() }. */
export function mountLiveAnalysis(container, opts) {
  const { streamUrl, clipUrl, zones = [], room = null, cameraId = null, apiKey = "",
    features = {} } = opts;
  // Источник: MJPEG-поток камеры (<img>) ИЛИ видеоролик/файл (<video>) — режим
  // «стены роликов» (#wall). Распознавание то же, отличается только хост-элемент.
  const isVideo = !!clipUrl;
  // Тумблеры «что распознаём» (по умолчанию всё включено). Читаются НА ЛЕТУ —
  // объект features можно мутировать снаружи (карточка стены), эффект сразу.
  const feat = (k) => features[k] !== false;
  container.innerHTML = "";
  container.classList.add("live-embed");

  // DOM: видео (MJPEG как <img> или ролик как <video>), оверлей-скелет,
  // heat-заливка, слой разметки зон, журнал, статус.
  const stage = document.createElement("div");
  stage.style.cssText = "position:relative;background:#060807;border:1px solid var(--bd,#444);border-radius:8px;overflow:hidden";
  const img = isVideo ? document.createElement("video") : document.createElement("img");
  img.crossOrigin = "anonymous";
  img.style.cssText = "display:block;width:100%";
  if (isVideo) { img.controls = true; img.loop = true; img.muted = true; img.playsInline = true; img.autoplay = true; }
  // Размеры медиа: у <video> — videoWidth/Height, у <img> — naturalWidth/Height.
  const mediaW = () => (isVideo ? img.videoWidth : img.naturalWidth);
  const mediaH = () => (isVideo ? img.videoHeight : img.naturalHeight);
  const heat = document.createElement("canvas");
  const skel = document.createElement("canvas");
  const edit = document.createElement("canvas"); // разметка ROI-зон (#256)
  for (const c of [heat, skel, edit]) c.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
  stage.append(img, heat, skel, edit);

  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:10px;align-items:center;margin:8px 0;font-size:13px;flex-wrap:wrap";
  const stopBtn = document.createElement("button");
  stopBtn.textContent = "Остановить анализ";
  const zonesBtn = document.createElement("button");
  // В режиме роликов (#wall) разметка зоны стола — ключевой шаг (иначе протирание
  // считается по всему кадру и ложит), поэтому кнопка заметнее и подписана явно.
  zonesBtn.textContent = isVideo ? "✎ Обвести стол (ROI)" : "Зоны ✎";
  if (!isVideo) zonesBtn.className = "sec";
  // Инструменты разметки (видны только в режиме редактирования зон).
  const tools = document.createElement("span");
  tools.style.cssText = "display:none;gap:6px;align-items:center";
  const typeSel = document.createElement("select");
  for (const [v, t] of [["table", "стол"], ["floor", "пол"], ["window", "окно"]]) {
    const o = document.createElement("option");
    o.value = v; o.textContent = t; typeSel.appendChild(o);
  }
  const delBtn = document.createElement("button");
  delBtn.textContent = "Удалить зону";
  delBtn.className = "sec";
  delBtn.style.display = "none";
  const hint = document.createElement("span");
  hint.style.cssText = "color:var(--muted,#888);font-size:12px";
  hint.textContent = "растяните прямоугольник; углы зон можно таскать";
  tools.append(typeSel, delBtn, hint);
  const status = document.createElement("span");
  status.style.color = "var(--muted,#888)";
  const cov = document.createElement("span");
  cov.style.cssText = "margin-left:auto;font-family:monospace;font-size:12px";
  bar.append(stopBtn, zonesBtn, tools, status, cov);

  const logBox = document.createElement("div");
  logBox.style.cssText = "max-height:220px;overflow:auto;border:1px solid var(--bd,#444);border-radius:8px;padding:6px;font-family:monospace;font-size:12.5px";
  container.append(stage, bar, logBox);

  const heatCtx = heat.getContext("2d");
  const ctx = skel.getContext("2d");
  const engine = new AnalysisEngine({ rois: zonesToRois(zones), gridWidth: 200 });
  const smooth = makeSmoother();
  const handPrev = {};
  let trail = [];               // последние позиции кистей — для backfill на старте уборки
  let prevCleanActive = false;  // фронт активности уборки
  let running = true, lastT = -1;

  const pad = (n) => String(n).padStart(2, "0");
  function log(text, color, isAct, imgData) {
    const d = new Date();
    const e = document.createElement("div");
    e.style.cssText = "padding:3px 4px;border-left:3px solid " + (color || "#3ef0a0") + (isAct ? ";font-weight:600;color:#fff" : "");
    e.textContent = `[${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}] ${text}`;
    if (imgData) {
      const im = document.createElement("img");
      im.src = imgData; im.style.cssText = "display:block;margin-top:4px;max-width:240px;border-radius:6px;cursor:pointer";
      im.onclick = () => { const a = document.createElement("a"); a.href = imgData; a.download = "shot-" + Date.now() + ".jpg"; a.click(); };
      e.appendChild(im);
    }
    logBox.appendChild(e); logBox.scrollTop = logBox.scrollHeight;
  }

  function postEvent(message, imgData) {
    if (!cameraId) return;
    const body = { room, message, payload: { origin: "browser", camera_id: cameraId } };
    if (imgData) body.image = imgData;
    fetch("/api/v1/analytics-events", {
      method: "POST", headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(body),
    }).catch(() => {});
  }

  /* отчёт о покрытии («протёрто на N%») → журнал/Grafana тем же контрактом,
     что у серверного воркера: type=coverage_report, payload {zone,zone_id,coverage_pct}.
     Прикладываем стоп-кадр (imgData) — чтобы в ленте был скриншот протёртого стола. */
  function postCoverage(e, imgData) {
    if (!cameraId) return;
    fetch("/api/v1/analytics-events", {
      method: "POST", headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({
        room, message: e.text, type: "coverage_report",
        image: imgData || undefined,
        payload: {
          origin: "browser", camera_id: cameraId, zone: e.coverage.zoneType,
          zone_id: e.coverage.zoneId == null ? null : e.coverage.zoneId,
          coverage_pct: e.coverage.pct,
        },
      }),
    }).catch(() => {});
  }

  /* Эвристика «белого халата» (порт uniform.py): по торсу (плечи 11/12, бёдра
     23/24) считаем яркость+насыщенность кадра; белый халат = ярко и неярко-цветно.
     Это индикатор, а не строгий контроль (путается на белой стене/пересвете). */
  const uCanvas = document.createElement("canvas");
  const uCtx = uCanvas.getContext("2d", { willReadFrequently: true });
  let uSince = -1, uFired = false; // трекер нарушения (как UniformViolationDetector)
  let uniformOkFired = false, uniformLostMs = 0; // трекер положительного «халат распознан»
  function uniformCheck(lm) {
    const idx = [11, 12, 24, 23];
    if (idx.some((i) => !lm[i] || (lm[i].visibility ?? 1) < 0.5)) return null;
    const xs = idx.map((i) => lm[i].x), ys = idx.map((i) => lm[i].y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const mw = mediaW(), mh = mediaH();
    if (!mw || x1 <= x0 || y1 <= y0) return null;
    uCanvas.width = 64; uCanvas.height = 64;
    try {
      uCtx.drawImage(img, x0 * mw, y0 * mh, (x1 - x0) * mw, (y1 - y0) * mh, 0, 0, 64, 64);
      const d = uCtx.getImageData(0, 0, 64, 64).data;
      let bSum = 0, sSum = 0, n = 0;
      for (let i = 0; i < d.length; i += 4) {
        const mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]);
        bSum += mx / 255; sSum += mx > 0 ? (mx - mn) / mx : 0; n++;
      }
      if (!n) return null;
      const brightness = bSum / n, saturation = sSum / n;
      // Пороги под реальное освещение объекта (замеры: халат 0.57–0.68 / 0.02–0.26).
      return { brightness, saturation, white: brightness >= 0.5 && saturation <= 0.35 };
    } catch { return null; }
  }
  function uniformTrack(white, nowMs) {
    if (white) { uSince = -1; uFired = false; return null; }
    if (uSince < 0) { uSince = nowMs; return null; }
    if (uFired) return null;
    const elapsed = (nowMs - uSince) / 1000;
    if (elapsed >= 5) { uFired = true; return elapsed; }
    return null;
  }
  function postUniform(message, imgData, u) {
    if (!cameraId) return;
    fetch("/api/v1/analytics-events", {
      method: "POST", headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({
        room, message, type: "uniform_violation", severity: "warning",
        image: imgData || undefined,
        payload: {
          origin: "browser", camera_id: cameraId, flag: "no_uniform",
          brightness: Math.round(u.brightness * 100) / 100,
          saturation: Math.round(u.saturation * 100) / 100,
        },
      }),
    }).catch(() => {});
  }

  const snapCanvas = document.createElement("canvas");
  function snapshot() {
    const W = skel.width, H = skel.height;
    if (!W || !H || !mediaW()) return null;
    const maxW = 720, sc = W > maxW ? maxW / W : 1, cw = Math.round(W * sc), ch = Math.round(H * sc);
    snapCanvas.width = cw; snapCanvas.height = ch;
    const x = snapCanvas.getContext("2d");
    try {
      x.drawImage(img, 0, 0, cw, ch);
      x.drawImage(heat, 0, 0, cw, ch);
      return snapCanvas.toDataURL("image/jpeg", 0.8);
    } catch { return null; } // поток без CORS-заголовков — стоп-кадр недоступен
  }

  function setSizes(w, h) {
    if (w && h && (skel.width !== w || skel.height !== h)) {
      skel.width = heat.width = edit.width = w;
      skel.height = heat.height = edit.height = h;
      if (editing) drawZones();
    }
  }

  /* ── Разметка ROI-зон прямо на живом видео (#256) ──
   * Прямоугольник растягивается мышью, тип берётся из селекта, сохранение —
   * сразу POST /cameras/{id}/zones; углы сохранённых зон таскаются (PATCH),
   * клик внутри зоны выделяет её для удаления. Движок подхватывает изменения
   * на лету: engine.rois переприсваивается после каждой правки. */
  const ZONE_COLORS = { table: "#2e7d32", floor: "#ef6c00", window: "#1565c0" };
  const editCtx = edit.getContext("2d");
  let editing = false;
  let liveZones = (zones || []).map((z) => ({ ...z })); // локальная копия зон БД
  let selected = -1;    // индекс выделенной зоны (для удаления)
  let rubber = null;    // {x0,y0,x1,y1} — растягиваемый прямоугольник
  let dragging = null;  // {zi, pi, moved} — перетаскиваемый угол зоны

  async function zoneApi(path, method, body) {
    const resp = await fetch("/api/v1" + path, {
      method,
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: body ? JSON.stringify(body) : undefined,
    });
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error((json.error && json.error.message) || "HTTP " + resp.status);
    return json.data;
  }

  /* Перечитать зоны из БД и отдать их движку (ядро видит правки сразу). */
  async function refreshZones() {
    const data = await zoneApi(`/cameras/${cameraId}/zones`, "GET");
    liveZones = data.items || [];
    engine.rois = zonesToRois(liveZones);
    if (selected >= liveZones.length) selected = -1;
    delBtn.style.display = selected >= 0 ? "" : "none";
    drawZones();
  }

  const clamp01 = (v) => Math.min(1, Math.max(0, v));
  /* Координаты события мыши → нормализованные [0..1] (по CSS-размеру слоя). */
  function normPos(ev) {
    const r = edit.getBoundingClientRect();
    return [clamp01((ev.clientX - r.left) / r.width), clamp01((ev.clientY - r.top) / r.height)];
  }
  /* Точка внутри полигона (ray casting) — для выделения зоны кликом. */
  function inPoly(x, y, pts) {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i], [xj, yj] = pts[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  function drawZones() {
    const W = edit.width, H = edit.height;
    editCtx.clearRect(0, 0, W, H);
    if (!editing) return;
    liveZones.forEach((z, zi) => {
      const color = ZONE_COLORS[z.zone_type] || "#888";
      editCtx.beginPath();
      z.polygon.forEach(([x, y], i) => (i ? editCtx.lineTo(x * W, y * H) : editCtx.moveTo(x * W, y * H)));
      editCtx.closePath();
      editCtx.lineWidth = zi === selected ? 4 : 2;
      editCtx.strokeStyle = color;
      editCtx.fillStyle = color + (zi === selected ? "55" : "33");
      editCtx.fill(); editCtx.stroke();
      // Углы — ручки перетаскивания.
      z.polygon.forEach(([x, y]) => {
        editCtx.beginPath(); editCtx.fillStyle = "#fff"; editCtx.strokeStyle = color;
        editCtx.arc(x * W, y * H, zi === selected ? 7 : 5, 0, 7); editCtx.fill(); editCtx.stroke();
      });
      // Подпись типа у первой вершины.
      const [lx, ly] = z.polygon[0];
      editCtx.font = `${Math.max(12, W * 0.018)}px system-ui`;
      editCtx.fillStyle = color;
      editCtx.fillText(zoneLabel(z), lx * W + 8, ly * H - 8);
    });
    if (rubber) {
      editCtx.setLineDash([6, 4]);
      editCtx.strokeStyle = "#3367d6"; editCtx.lineWidth = 2;
      editCtx.fillStyle = "rgba(51,103,214,0.15)";
      const x = Math.min(rubber.x0, rubber.x1) * W, y = Math.min(rubber.y0, rubber.y1) * H;
      const w = Math.abs(rubber.x1 - rubber.x0) * W, h = Math.abs(rubber.y1 - rubber.y0) * H;
      editCtx.fillRect(x, y, w, h); editCtx.strokeRect(x, y, w, h);
      editCtx.setLineDash([]);
    }
  }

  function onDown(ev) {
    ev.preventDefault();
    const [x, y] = normPos(ev);
    const r = edit.getBoundingClientRect();
    const grab = 10 / Math.min(r.width, r.height); // радиус захвата угла, ~10px CSS
    // 1) угол существующей зоны → перетаскивание (выделенная зона — приоритетнее).
    const order = selected >= 0 ? [selected, ...liveZones.keys()] : [...liveZones.keys()];
    for (const zi of order) {
      const z = liveZones[zi];
      if (!z) continue;
      const pi = z.polygon.findIndex(([px, py]) => Math.hypot(px - x, py - y) < grab);
      if (pi >= 0) { dragging = { zi, pi, moved: false }; selected = zi; drawZones(); return; }
    }
    // 2) клик внутри зоны → выделение (для удаления).
    const hit = liveZones.findIndex((z) => inPoly(x, y, z.polygon));
    if (hit >= 0) {
      selected = hit;
      delBtn.style.display = "";
      drawZones();
      return;
    }
    // 3) пустое место → начинаем растягивать прямоугольник новой зоны.
    selected = -1; delBtn.style.display = "none";
    rubber = { x0: x, y0: y, x1: x, y1: y };
    drawZones();
  }
  function onMove(ev) {
    if (!editing || (!rubber && !dragging)) return;
    const [x, y] = normPos(ev);
    if (dragging) {
      const z = liveZones[dragging.zi];
      z.polygon[dragging.pi] = [x, y];
      dragging.moved = true;
    } else {
      rubber.x1 = x; rubber.y1 = y;
    }
    drawZones();
  }
  async function onUp() {
    if (dragging) {
      const { zi, moved } = dragging;
      dragging = null;
      if (!moved) return;
      const z = liveZones[zi];
      try {
        await zoneApi(`/zones/${z.id}`, "PATCH", { polygon: z.polygon });
        log(`Зона «${zoneLabel(z)}» изменена`, "#3367d6");
      } catch (e) {
        log("Не удалось изменить зону: " + e.message, "#ff5d6c");
      }
      refreshZones().catch(() => {});
      return;
    }
    if (rubber) {
      const { x0, y0, x1, y1 } = rubber;
      rubber = null;
      // Слишком маленький прямоугольник — считаем случайным кликом.
      if (Math.abs(x1 - x0) < 0.03 || Math.abs(y1 - y0) < 0.03) { drawZones(); return; }
      const xa = Math.min(x0, x1), xb = Math.max(x0, x1);
      const ya = Math.min(y0, y1), yb = Math.max(y0, y1);
      const polygon = [[xa, ya], [xb, ya], [xb, yb], [xa, yb]];
      try {
        await zoneApi(`/cameras/${cameraId}/zones`, "POST", { zone_type: typeSel.value, polygon });
        log(`Зона «${typeSel.options[typeSel.selectedIndex].text}» сохранена`, "#3367d6");
      } catch (e) {
        log("Не удалось сохранить зону: " + e.message, "#ff5d6c");
      }
      refreshZones().catch(() => {});
    }
  }
  edit.addEventListener("pointerdown", onDown);
  edit.addEventListener("pointermove", onMove);
  edit.addEventListener("pointerup", onUp);
  edit.addEventListener("pointerleave", onUp);

  delBtn.onclick = async () => {
    const z = liveZones[selected];
    if (!z) return;
    try {
      await zoneApi(`/zones/${z.id}`, "DELETE");
      log(`Зона «${zoneLabel(z)}» удалена`, "#3367d6");
    } catch (e) {
      log("Не удалось удалить зону: " + e.message, "#ff5d6c");
    }
    selected = -1; delBtn.style.display = "none";
    refreshZones().catch(() => {});
  };

  zonesBtn.onclick = () => {
    editing = !editing;
    zonesBtn.textContent = editing ? "Готово" : "Зоны ✎";
    zonesBtn.className = editing ? "" : "sec";
    tools.style.display = editing ? "inline-flex" : "none";
    edit.style.pointerEvents = editing ? "auto" : "none";
    edit.style.cursor = editing ? "crosshair" : "";
    if (editing && cameraId) refreshZones().catch((e) => log("Зоны: " + e.message, "#ff5d6c"));
    else { selected = -1; delBtn.style.display = "none"; rubber = null; dragging = null; drawZones(); }
  };
  if (!cameraId) zonesBtn.style.display = "none"; // без камеры зоны сохранять некуда

  /* сбросить заливку: и визуальный heat-канвас, и сетку покрытия движка (как в
     PoC после стоп-кадра/в начале сессии) — иначе % копится между уборками. */
  function clearHeat() {
    heatCtx.clearRect(0, 0, heat.width, heat.height);
    engine.heat.clear();
    handPrev[15] = handPrev[16] = undefined;
  }

  // Плавное затухание заливки протирания (фидбэк: закрашивание «висело» и не
  // сбрасывалось). Каждый кадр гасим heat-канвас на ~4%; во время уборки
  // paintHands дорисовывает быстрее, поэтому след виден, а после остановки за
  // ~2–3 c исчезает. lastWipeMs — когда уборка была активна в последний раз.
  let lastWipeMs = 0;
  let lastCovReportMs = 0; // когда последний раз слали периодический отчёт о покрытии
  function fadeHeat() {
    heatCtx.save();
    heatCtx.globalCompositeOperation = "destination-out";
    heatCtx.fillStyle = "rgba(0,0,0,0.04)";
    heatCtx.fillRect(0, 0, heat.width, heat.height);
    heatCtx.restore();
  }

  /* путь обрезки по полигонам зоны (немного расширен) — заливка не вылезает за зону */
  function heatClipPath(polys) {
    const W = heat.width, H = heat.height;
    heatCtx.beginPath();
    polys.forEach((p) => {
      const cx = p.reduce((a, q) => a + q[0], 0) / p.length, cy = p.reduce((a, q) => a + q[1], 0) / p.length;
      p.forEach((pt, i) => {
        const ex = cx + (pt[0] - cx) * 1.08, ey = cy + (pt[1] - cy) * 1.08, x = ex * W, y = ey * H;
        i ? heatCtx.lineTo(x, y) : heatCtx.moveTo(x, y);
      });
      heatCtx.closePath();
    });
  }

  /* заливка «протёртости»: мазок радиусом из ширины кадра (как в ядре/PoC) */
  function stamp(a, b, color) {
    const W = heat.width, H = heat.height, r = Math.max(14, Math.min(W, H) * engine.lastTorso * 0.62);
    const bx = b.x * W, by = b.y * H;
    if (a) {
      const ax = a.x * W, ay = a.y * H;
      if (Math.hypot(bx - ax, by - ay) < W * 0.3) {
        heatCtx.strokeStyle = color + "33"; heatCtx.lineWidth = r * 1.4; heatCtx.lineCap = "round";
        heatCtx.beginPath(); heatCtx.moveTo(ax, ay); heatCtx.lineTo(bx, by); heatCtx.stroke();
      }
    }
    const g = heatCtx.createRadialGradient(bx, by, 0, bx, by, r);
    g.addColorStop(0, color + "4d"); g.addColorStop(1, color + "00");
    heatCtx.fillStyle = g; heatCtx.beginPath(); heatCtx.arc(bx, by, r, 0, 7); heatCtx.fill();
  }
  /* крашу рабочие кисти текущего кадра, обрезая по зоне уборки (engine.cleanClip) */
  function paintHands(lm) {
    const idx = engine.cleanHandIdx && engine.cleanHandIdx.length ? engine.cleanHandIdx : [];
    if (!idx.length) return;
    const clip = engine.cleanClip && engine.cleanClip.length;
    if (clip) { heatCtx.save(); heatClipPath(engine.cleanClip); heatCtx.clip(); }
    idx.forEach((wr) => { const pt = handPoint(lm, wr); stamp(handPrev[wr], pt, engine.cleanColor); handPrev[wr] = pt; });
    if (clip) heatCtx.restore();
  }
  /* на старте уборки дорисовываю накопленный след (первые движения до детекта) */
  function backfillHeat() {
    const idx = engine.cleanHandIdx && engine.cleanHandIdx.length ? engine.cleanHandIdx : [];
    if (!idx.length || !trail.length) return;
    const clip = engine.cleanClip && engine.cleanClip.length;
    if (clip) { heatCtx.save(); heatClipPath(engine.cleanClip); heatCtx.clip(); }
    idx.forEach((wr) => {
      const key = wr === 16 ? "p16" : "p15"; let prev = null;
      trail.forEach((t) => { if (t[key]) { stamp(prev, t[key], engine.cleanColor); prev = t[key]; } });
      if (prev) handPrev[wr] = prev;
    });
    if (clip) heatCtx.restore();
  }
  function pushTrail(lm) {
    trail.push({ p15: handPoint(lm, 15), p16: handPoint(lm, 16) });
    if (trail.length > 60) trail.shift();
  }

  function draw(lm) {
    const W = skel.width, H = skel.height;
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = Math.max(2, W * 0.0035); ctx.strokeStyle = "rgba(62,240,160,0.55)";
    ctx.shadowColor = "rgba(62,240,160,0.8)"; ctx.shadowBlur = 8;
    CONN.forEach(([a, b]) => {
      const p = lm[a], q = lm[b]; if (vis(p) < 0.4 || vis(q) < 0.4) return;
      ctx.beginPath(); ctx.moveTo(p.x * W, p.y * H); ctx.lineTo(q.x * W, q.y * H); ctx.stroke();
    });
    ctx.shadowBlur = 0;
    lm.forEach((p, i) => {
      if (vis(p) < 0.4) return; const key = i === 15 || i === 16;
      ctx.beginPath(); ctx.fillStyle = key ? "#fff" : "#3ef0a0"; ctx.arc(p.x * W, p.y * H, key ? W * 0.007 : W * 0.004, 0, 7); ctx.fill();
    });
  }

  function updateCov() {
    const rois = engine.rois;
    rois.forEach((r) => { r.cov = engine.heat.coverage(r.pts); });
    cov.textContent = rois.length
      ? "покрытие · " + rois.map((r) => (r.name || r.type) + " " + (r.cov || 0) + "%").join(" · ")
      : "";
  }

  let covT = 0;
  function loop() {
    if (!running) return;
    const w = mediaW(), h = mediaH();
    if (w > 0 && performance.now() - lastT >= 30) {
      lastT = performance.now();
      setSizes(w, h);
      try {
        const res = _landmarker.detectForVideo(img, performance.now());
        if (res.landmarks && res.landmarks.length) {
          status.textContent = "трекинг активен";
          const world = res.worldLandmarks && res.worldLandmarks[0];
          const lm = smooth(res.landmarks[0]);
          draw(lm);
          const evs = engine.analyze(lm, world, performance.now());
          let resetHeat = false;
          // ВАЖНО: протирание распознаём ТОЛЬКО при явно заданной зоне стола.
          // Без зоны (engine.rois пуст) уборку не детектим вовсе (фидбэк: без зоны
          // махи руками ложно засчитывались как протирание).
          const hasZone = engine.rois.length > 0;
          for (const e of evs) {
            const clean = ["wipe", "mop", "sweep", "window"].includes(e.action);
            // Уборка/покрытие — по тумблеру «wipe» И только при заданной зоне.
            if ((e.coverage || (e.isAct && clean)) && (!feat("wipe") || !hasZone)) continue;
            if (e.isAct && !clean && !feat("actions")) continue;
            if (!e.isAct && !e.coverage && !feat("poses")) continue;
            // Для уборки всегда делаем стоп-кадр — и на НАЧАЛО, и на конец.
            const shot = (e.snapshot || clean) ? snapshot() : null;
            log(e.text, e.color, e.isAct, shot);
            if (e.isAct) postEvent(e.text, shot);   // действие (+стоп-кадр) → журнал/Grafana
            if (e.coverage) postCoverage(e, snapshot()); // «протёрто на N%» (+кадр) → журнал
            // после КОНЦА уборки сбрасываем заливку и % (стоп-кадр конца уже снят).
            if (e.snapshot && clean) resetHeat = true;
          }
          if (resetHeat) clearHeat();
          const cleanActive = hasZone && (engine.actState.wipe || engine.actState.mop
            || engine.actState.sweep || engine.actState.window);
          if (cleanActive && !prevCleanActive) backfillHeat(); // дорисовать след начала уборки
          prevCleanActive = cleanActive;
          if (cleanActive && feat("wipe")) { paintHands(lm); lastWipeMs = performance.now(); }
          // Периодический стоп-кадр покрытия во время уборки (раз в ~4 c): отчёт с %
          // и закрашенной зоной появляется, даже если уборка непрерывная (конца нет).
          if (cleanActive && feat("wipe") && hasZone) {
            if (!lastCovReportMs || performance.now() - lastCovReportMs > 4000) {
              lastCovReportMs = performance.now();
              const covShot = snapshot();
              engine.rois.forEach((r) => {
                const pct = Math.round(engine.heat.coverage(r.pts) || 0);
                if (pct <= 0) return;
                const name = r.name || r.type;
                const txt = `${name}: протёрто ${pct}%`;
                log(txt, "#46d160", false, covShot);
                postCoverage({ text: txt, coverage: { zoneType: r.type, zoneId: r.zoneId, pct } }, covShot);
              });
            }
          } else { lastCovReportMs = 0; }
          pushTrail(lm);
          // Эвристика «белого халата» — только при включённом тумблере «Халат».
          if (feat("uniform")) {
            const u = uniformCheck(lm);
            if (u) {
              ctx.save();
              ctx.font = `${Math.max(13, skel.width * 0.02)}px system-ui`;
              ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.6)";
              const badge = u.white ? "халат: ✓" : "халат: ✗";
              ctx.strokeText(badge, 10, 26); ctx.fillStyle = u.white ? "#3ef0a0" : "#e0b400";
              ctx.fillText(badge, 10, 26); ctx.restore();
              // Положительное событие «Халат распознан» (раз за эпизод) + стоп-кадр.
              if (u.white) {
                if (!uniformOkFired) {
                  uniformOkFired = true;
                  const okShot = snapshot();
                  log("Халат распознан (спецодежда в норме)", "#3ef0a0", true, okShot);
                  postEvent("Халат распознан (спецодежда в норме)", okShot);
                }
                uniformLostMs = 0;
              } else {
                if (!uniformLostMs) uniformLostMs = performance.now();
                if (performance.now() - uniformLostMs > 2000) uniformOkFired = false;
              }
              const dur = uniformTrack(u.white, performance.now());
              if (dur != null) {
                const shot = snapshot();
                const msg = `Человек без спецодежды (белого халата) дольше ${Math.round(dur)} с`;
                log(msg, "#e0b400", true, shot); postUniform(msg, shot, u);
              }
            }
          }
        } else {
          status.textContent = "не вижу человека"; ctx.clearRect(0, 0, skel.width, skel.height);
        }
      } catch { status.textContent = "кадр недоступен (CORS?)"; }
      // Гасим заливку ТОЛЬКО спустя ~1.3 c после остановки уборки: стоп-кадр КОНЦА
      // протирания формируется через ~0.6 c после рук — он должен застать зону
      // полностью закрашенной, а не выцветшей.
      if (lastWipeMs && performance.now() - lastWipeMs > 1300) fadeHeat();
      // Через ~3.5 c простоя — полный сброс (и заливки, и % покрытия).
      if (lastWipeMs && performance.now() - lastWipeMs > 3500) { clearHeat(); lastWipeMs = 0; }
      if (performance.now() - covT >= 1000) { covT = performance.now(); updateCov(); }
    }
    requestAnimationFrame(loop);
  }

  function stop() {
    if (!running) return;
    running = false;
    if (isVideo) { try { img.pause(); } catch { /* уже не играет */ } }
    img.src = "";
    log("Сессия остановлена", "#ffffff", true);
  }
  stopBtn.onclick = stop;

  status.textContent = "загрузка модели…";
  initModel().then(() => {
    if (isVideo) {
      status.textContent = "загрузка ролика…";
      img.addEventListener("loadeddata", () => setSizes(mediaW(), mediaH()));
      img.src = clipUrl;
    } else {
      status.textContent = "подключение к потоку…";
      img.onload = () => { setSizes(img.naturalWidth, img.naturalHeight); };
      img.src = streamUrl;
    }
    log("Сессия начата", "#ffffff", true);
    loop();
  }).catch((e) => { status.textContent = "ошибка: " + e.message; });

  return { stop };
}
