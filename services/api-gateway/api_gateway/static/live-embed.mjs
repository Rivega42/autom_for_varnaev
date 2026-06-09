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

/* зоны БД (zone_type/polygon/id) → ROI ядра (type/pts/name/zoneId) */
function zonesToRois(zones) {
  const RU = { table: "стол", floor: "пол", window: "окно" };
  return (zones || []).map((z) => ({
    type: z.zone_type, pts: z.polygon, zoneId: z.id, name: z.note || RU[z.zone_type] || z.zone_type, cov: 0,
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
  const { streamUrl, zones = [], room = null, cameraId = null, apiKey = "" } = opts;
  container.innerHTML = "";
  container.classList.add("live-embed");

  // DOM: видео (MJPEG как <img>), оверлей-скелет, heat-заливка, журнал, статус.
  const stage = document.createElement("div");
  stage.style.cssText = "position:relative;background:#060807;border:1px solid var(--bd,#444);border-radius:8px;overflow:hidden";
  const img = document.createElement("img");
  img.crossOrigin = "anonymous";
  img.style.cssText = "display:block;width:100%";
  const heat = document.createElement("canvas");
  const skel = document.createElement("canvas");
  for (const c of [heat, skel]) c.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
  stage.append(img, heat, skel);

  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:10px;align-items:center;margin:8px 0;font-size:13px";
  const stopBtn = document.createElement("button");
  stopBtn.textContent = "Остановить анализ";
  const status = document.createElement("span");
  status.style.color = "var(--muted,#888)";
  const cov = document.createElement("span");
  cov.style.cssText = "margin-left:auto;font-family:monospace;font-size:12px";
  bar.append(stopBtn, status, cov);

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

  const snapCanvas = document.createElement("canvas");
  function snapshot() {
    const W = skel.width, H = skel.height;
    if (!W || !H || !img.naturalWidth) return null;
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
      skel.width = heat.width = w; skel.height = heat.height = h;
    }
  }

  /* сбросить заливку: и визуальный heat-канвас, и сетку покрытия движка (как в
     PoC после стоп-кадра/в начале сессии) — иначе % копится между уборками. */
  function clearHeat() {
    heatCtx.clearRect(0, 0, heat.width, heat.height);
    engine.heat.clear();
    handPrev[15] = handPrev[16] = undefined;
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
    const w = img.naturalWidth, h = img.naturalHeight;
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
          for (const e of evs) {
            const shot = e.snapshot ? snapshot() : null;
            log(e.text, e.color, e.isAct, shot);
            if (e.isAct) postEvent(e.text, shot);   // действие (+стоп-кадр) → журнал/Grafana
            // сброс заливки/% — только после ЗАВЕРШЕНИЯ уборки; стоп-кадр
            // падения/SOS посреди уборки покрытие не трогает
            if (e.snapshot && ["wipe", "mop", "sweep", "window"].includes(e.action)) resetHeat = true;
          }
          if (resetHeat) clearHeat();
          const cleanActive = engine.actState.wipe || engine.actState.mop || engine.actState.sweep || engine.actState.window;
          if (cleanActive && !prevCleanActive) backfillHeat(); // дорисовать след начала уборки
          prevCleanActive = cleanActive;
          if (cleanActive) paintHands(lm);
          pushTrail(lm);
        } else {
          status.textContent = "не вижу человека"; ctx.clearRect(0, 0, skel.width, skel.height);
        }
      } catch { status.textContent = "кадр недоступен (CORS?)"; }
      if (performance.now() - covT >= 1000) { covT = performance.now(); updateCov(); }
    }
    requestAnimationFrame(loop);
  }

  function stop() {
    if (!running) return;
    running = false; img.src = "";
    log("Сессия остановлена", "#ffffff", true);
  }
  stopBtn.onclick = stop;

  status.textContent = "загрузка модели…";
  initModel().then(() => {
    status.textContent = "подключение к потоку…";
    img.onload = () => { setSizes(img.naturalWidth, img.naturalHeight); };
    img.src = streamUrl;
    log("Сессия начата", "#ffffff", true);
    loop();
  }).catch((e) => { status.textContent = "ошибка: " + e.message; });

  return { stop };
}
