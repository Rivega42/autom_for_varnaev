"use strict";
// GUI настройки видеоаналитики: камеры, тумблеры функций, разметка ROI-зон.
// Общается с api-gateway по REST (docs/03_API_CONTRACT.md §3.5), ключ X-API-Key
// хранится в localStorage. Кадр-превью грузится с /cameras/{id}/snapshot.

const API = "/api/v1";
const $ = (id) => document.getElementById(id);

let cameras = [];
let current = null; // выбранная камера
let points = []; // вершины текущего полигона (нормированные [0..1])
let frameImg = null; // загруженный кадр (Image)
let zonePolys = []; // сохранённые ROI-зоны выбранной камеры (для наложения)
let liveTimer = null; // таймер «живого» обновления кадра
let eventsTimer = null; // таймер обновления ленты событий

const keyInput = $("apikey");
keyInput.value = localStorage.getItem("apiKey") || "";
keyInput.addEventListener("change", () => localStorage.setItem("apiKey", keyInput.value));

function msg(text, ok = true) {
  const el = $("msg");
  el.textContent = text;
  el.style.color = ok ? "#cdf" : "#ffd0d0";
}

/* Индикатор состояния ключа API в шапке (#321): принят / не принят. */
function setKeyState(ok) {
  const el = $("keystate");
  if (!el) return;
  el.textContent = ok ? "ключ принят" : "ключ не принят";
  el.className = ok ? "ok" : "bad";
}

function headers(json = true) {
  const h = { "X-API-Key": keyInput.value };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function api(path, opts = {}) {
  const resp = await fetch(API + path, { headers: headers(opts.body != null), ...opts });
  if (!resp.ok) {
    let detail = resp.status;
    try {
      detail = (await resp.json()).error?.message || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return resp.status === 200 ? (await resp.json()).data : null;
}

// ── Лицензия: баннер тарифа/расхода и ввод ключа (#335) ──
// Лимиты выводятся из тарифа (демо — 1/1/1; ключ расширяет). Баннер показывает
// расход по каждому лимиту и подсвечивает превышение/проблему с ключом.
const LICENSE_ROLES = [
  ["rooms", "помещения"],
  ["cameras", "камеры"],
  ["nodes", "узлы"],
];
const LICENSE_STATUS = {
  demo: "демо",
  active: "лицензия активна",
  expired: "подписка истекла — действуют демо-лимиты",
  invalid: "ключ недействителен — действуют демо-лимиты",
};

// Тревожный тон — если ключ просрочен/недействителен либо превышен любой лимит.
function licenseOverLimit(info) {
  return LICENSE_ROLES.some(([k]) => {
    const lim = info.limits[k];
    return lim != null && (info.usage[k] || 0) > lim;
  });
}

function renderLicense(info) {
  const bar = $("licbar");
  if (!bar) return;
  bar.hidden = false;
  const warn = info.status === "expired" || info.status === "invalid" || licenseOverLimit(info);
  bar.className = "licbar " + (warn ? "warn" : info.status === "active" ? "ok" : "");

  let tier = `Тариф: ${info.tier}`;
  if (info.customer) tier += ` · ${info.customer}`;
  $("lictier").textContent = tier;

  const parts = LICENSE_ROLES.map(([k, label]) => {
    const used = info.usage[k] || 0;
    const lim = info.limits[k];
    const over = lim != null && used > lim;
    return `${label} ${used}/${lim == null ? "∞" : lim}${over ? " (превышено)" : ""}`;
  });
  let note = LICENSE_STATUS[info.status] || info.status;
  if (info.expires) note += `, до ${info.expires}`;
  $("licusage").textContent = `${parts.join(" · ")} — ${note}`;
}

async function loadLicense() {
  try {
    renderLicense(await api("/license"));
  } catch (_) {
    // Баннер некритичен (например, ключ API ещё не введён) — молча скрываем.
    const bar = $("licbar");
    if (bar) bar.hidden = true;
  }
}

// Применить/сбросить лицензионный ключ из GUI (PUT /license, нужна роль admin).
async function applyLicenseKey(key) {
  try {
    renderLicense(await api("/license", { method: "PUT", body: JSON.stringify({ key }) }));
    $("lickey").value = "";
    $("lickeyForm").hidden = true;
    msg(key ? "Лицензионный ключ применён" : "Ключ сброшен — демо-лимиты");
    loadAll(); // лимиты изменились — перечитать списки и счётчики расхода
  } catch (e) {
    msg("Ошибка применения ключа: " + e.message, false);
  }
}

// ── Интеграция с АУРА: тумблер режима (#352) ──
// Выкл — контур автономен (разъёмы /integration/* → 501); вкл — открыты для АУРА.
// Состояние хранится на сервере (app_config), переключается без перезапуска.
function renderAura(enabled) {
  $("aura_enabled").checked = enabled;
  $("aura_state").textContent = enabled ? "включена" : "выключена (автономный режим)";
}

async function loadAuraStatus() {
  try {
    renderAura((await api("/aura/status")).enabled);
  } catch (_) {
    /* некритично (например, ключ API ещё не введён) */
  }
}

async function toggleAura() {
  try {
    const d = await api("/aura/status", {
      method: "PUT",
      body: JSON.stringify({ enabled: $("aura_enabled").checked }),
    });
    renderAura(d.enabled);
    msg(d.enabled ? "Интеграция с АУРА включена" : "Интеграция с АУРА выключена");
  } catch (e) {
    msg("Ошибка переключения интеграции: " + e.message, false);
    loadAuraStatus(); // откатить чекбокс к фактическому состоянию
  }
}

// ── Камеры ──

async function loadCameras() {
  try {
    const data = await api("/cameras");
    cameras = data.items;
    renderCamList();
    fillCameraSelect();
    msg(`Камер: ${cameras.length}`);
    setKeyState(true);
  } catch (e) {
    msg("Ошибка загрузки камер: " + e.message, false);
    setKeyState(false);
  }
}

// Поток для воркера: go2rtc ретранслирует камеру по имени.
function streamRef(cam) {
  return `rtsp://media-gateway:8554/${cam.name}`;
}

// Выпадающий список камер в форме расписания (для привязки camera_id).
function fillCameraSelect() {
  const sel = $("sc_camera");
  if (!sel) return;
  sel.innerHTML = '<option value="">камера (опц.)</option>';
  for (const cam of cameras) {
    const opt = document.createElement("option");
    opt.value = cam.id;
    opt.textContent = cam.name;
    sel.appendChild(opt);
  }
}

// Браузерный живой анализ (порт PoC) — НАТИВНО в карточке камеры (без iframe):
// скелет, распознавание, журнал, стоп-кадры поверх MJPEG-потока, на едином ядре
// analysis-core (то же, что и сервер). Монтируется в #liveMount.
let liveHandle = null;
let liveOpening = false; // защёлка от двойного клика, пока идёт async-открытие
function stopLiveAnalysis() {
  if (liveHandle) {
    liveHandle.stop();
    liveHandle = null;
  }
  const mount = $("liveMount");
  if (mount) {
    mount.hidden = true;
    mount.innerHTML = "";
  }
  const btn = $("liveAnalysis");
  if (btn) btn.textContent = "Живой анализ (скелет)";
}

async function openLiveAnalysis() {
  if (!current) {
    msg("Сначала выберите камеру", false);
    return;
  }
  if (liveHandle) {
    stopLiveAnalysis();
    return;
  }
  if (liveOpening) return; // второй клик до завершения await — второй движок не монтируем
  liveOpening = true;
  const key = keyInput.value;
  try {
    // ROI-зоны камеры из БД — те же полигоны, что и серверная разметка.
    const z = await api(`/cameras/${current.id}/zones`);
    const { mountLiveAnalysis } = await import("./live-embed.mjs");
    const streamUrl = `${API}/cameras/${current.id}/stream.mjpeg?api_key=${encodeURIComponent(key)}`;
    const mount = $("liveMount");
    mount.hidden = false;
    liveHandle = mountLiveAnalysis(mount, {
      streamUrl,
      zones: z.items || [],
      room: current.room,
      cameraId: current.id,
      apiKey: key,
    });
    $("liveAnalysis").textContent = "Скрыть анализ";
  } catch (e) {
    msg("Ошибка живого анализа: " + e.message, false);
  } finally {
    liveOpening = false;
  }
}

// Разовый запуск анализа выбранной камеры (без curl/UUID).
async function runAnalysisNow() {
  if (!current) {
    msg("Сначала выберите камеру", false);
    return;
  }
  const body = {
    source_type: "stream",
    source_ref: streamRef(current),
    pipeline: "pose_v1",
    room: current.room,
    camera_id: current.id,
  };
  try {
    await api("/analysis-tasks", { method: "POST", body: JSON.stringify(body) });
    msg("Анализ запущен — события появятся через ~30–60 с");
  } catch (e) {
    msg("Ошибка запуска анализа: " + e.message, false);
  }
}

function renderCamList() {
  const ul = $("camlist");
  ul.innerHTML = "";
  $("emptyhint").hidden = cameras.length > 0;
  for (const cam of cameras) {
    const li = document.createElement("li");
    li.textContent = cam.name + (cam.enabled ? "" : " (выкл)");
    li.className = (current && current.id === cam.id ? "active " : "") + (cam.enabled ? "" : "off");
    li.onclick = () => selectCamera(cam);
    ul.appendChild(li);
  }
}

function feature(cam, name) {
  // null/отсутствие ключа = функция включена.
  return cam.analytics == null || cam.analytics[name] !== false;
}

function selectCamera(cam) {
  current = cam;
  points = [];
  frameImg = null;
  zonePolys = [];
  stopLive();
  stopVideo();
  stopLiveAnalysis();
  $("editor").hidden = false;
  $("camname").textContent = cam.name + " · " + cam.room;
  $("enabled").checked = cam.enabled;
  $("f_pose").checked = feature(cam, "pose");
  $("f_actions").checked = feature(cam, "actions");
  $("f_uniform").checked = feature(cam, "uniform");
  $("f_coverage").checked = feature(cam, "coverage");
  renderCamList();
  draw();
  loadZones();
  // Лента событий камеры — обновляется в фоне, пока выбрана камера.
  loadCameraEvents();
  if (!eventsTimer) eventsTimer = setInterval(loadCameraEvents, 3000);
}

async function saveCamera() {
  const body = {
    enabled: $("enabled").checked,
    analytics: {
      pose: $("f_pose").checked,
      actions: $("f_actions").checked,
      uniform: $("f_uniform").checked,
      coverage: $("f_coverage").checked,
    },
  };
  try {
    current = await api(`/cameras/${current.id}`, { method: "PATCH", body: JSON.stringify(body) });
    cameras = cameras.map((c) => (c.id === current.id ? current : c));
    renderCamList();
    msg("Настройки камеры сохранены");
  } catch (e) {
    msg("Ошибка сохранения: " + e.message, false);
  }
}

// Мягкое удаление камеры (#329): скрывает камеру и её ROI-зоны; история анализа
// и стоп-кадры сохраняются. Чтобы временно отключить камеру (с сохранением в
// списке) — снимите галочку «камера включена».
async function deleteCamera() {
  if (!current) return;
  const ok = window.confirm(
    `Удалить камеру «${current.name}»?\n\n` +
      "Камера и её ROI-зоны исчезнут из справочника. История анализа и " +
      "стоп-кадры сохранятся. Восстановить камеру через интерфейс нельзя.",
  );
  if (!ok) return;
  try {
    await api(`/cameras/${current.id}`, { method: "DELETE" });
    const name = current.name;
    current = null;
    stopLive();
    stopVideo();
    stopLiveAnalysis();
    $("editor").hidden = true;
    await loadCameras();
    msg(`Камера «${name}» удалена`);
  } catch (e) {
    msg("Ошибка удаления камеры: " + e.message, false);
  }
}

// ── Кадр-превью и разметка ──

async function loadFrame() {
  try {
    const resp = await fetch(`${API}/cameras/${current.id}/snapshot`, { headers: headers(false) });
    if (!resp.ok) throw new Error(resp.status);
    const blob = await resp.blob();
    const img = new Image();
    img.onload = () => {
      frameImg = img;
      draw();
    };
    img.src = URL.createObjectURL(blob);
    msg("Кадр загружен");
  } catch (e) {
    msg("Кадр недоступен (проверьте go2rtc/имя потока): " + e.message, false);
  }
}

// «Почти живой» просмотр: периодически перезагружаем кадр-снимок (go2rtc).
// Это не видеопоток, а обновление кадра раз в ~2 c — без стрим-прокси/нагрузки.
function stopLive() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
  const btn = $("liveToggle");
  if (btn) btn.textContent = "Живой просмотр";
}

function toggleLive() {
  if (!current) {
    msg("Сначала выберите камеру", false);
    return;
  }
  if (liveTimer) {
    stopLive();
    return;
  }
  loadFrame();
  liveTimer = setInterval(loadFrame, 2000);
  $("liveToggle").textContent = "Стоп";
}

// Живой MJPEG-видеопоток камеры (плавное видео) через тег <img>.
// Ключ передаётся в query — <img> не шлёт заголовки (медиа-авторизация).
function stopVideo() {
  const img = $("livevideo");
  img.hidden = true;
  img.src = ""; // обрывает MJPEG-соединение
  $("canvas").style.display = "";
  $("videoToggle").textContent = "Видео (поток)";
}

function toggleVideo() {
  if (!current) {
    msg("Сначала выберите камеру", false);
    return;
  }
  const img = $("livevideo");
  if (!img.hidden) {
    stopVideo();
    return;
  }
  stopLive(); // живое видео и обновление кадра — взаимоисключающие
  const key = encodeURIComponent(keyInput.value);
  img.src = `${API}/cameras/${current.id}/stream.mjpeg?api_key=${key}`;
  img.hidden = false;
  $("canvas").style.display = "none";
  $("videoToggle").textContent = "Стоп видео";
}

// Лента событий аналитики по помещению выбранной камеры (онлайн, поллинг).
async function loadCameraEvents() {
  if (!current) return;
  try {
    const data = await api(`/events?room=${encodeURIComponent(current.room)}&limit=20`);
    const tbody = $("camevents").querySelector("tbody");
    tbody.innerHTML = "";
    for (const ev of data.items.filter((e) => e.source === "analytics")) {
      const tr = document.createElement("tr");
      const cells = [new Date(ev.ts).toLocaleTimeString(), ev.type, ev.message];
      for (const text of cells) {
        const td = document.createElement("td");
        td.textContent = text; // textContent: сообщение приходит из БД
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  } catch (_) {
    // Лента не критична — молча пропускаем сбой опроса.
  }
}

const canvas = $("canvas");
const ctx = canvas.getContext("2d");

canvas.addEventListener("click", (ev) => {
  const r = canvas.getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width;
  const y = (ev.clientY - r.top) / r.height;
  points.push([Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]);
  draw();
});

// Цвета ROI-зон по типу (для наложения на кадр).
const ZONE_COLORS = { table: "#2e7d32", floor: "#ef6c00", window: "#1565c0" };

function drawPoly(poly, color, fill) {
  if (!poly.length) return;
  ctx.beginPath();
  poly.forEach(([x, y], i) => {
    const px = x * canvas.width;
    const py = y * canvas.height;
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  });
  if (poly.length > 2) ctx.closePath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
  if (fill) {
    ctx.fillStyle = color + "33"; // ~20% прозрачности (8-значный hex)
    ctx.fill();
  }
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (frameImg) ctx.drawImage(frameImg, 0, 0, canvas.width, canvas.height);
  else {
    ctx.fillStyle = "#eee";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
  // Сохранённые ROI-зоны поверх кадра.
  for (const z of zonePolys) {
    drawPoly(z.polygon, ZONE_COLORS[z.type] || "#888", true);
  }
  if (points.length) {
    ctx.beginPath();
    points.forEach(([x, y], i) => {
      const px = x * canvas.width;
      const py = y * canvas.height;
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    if (points.length > 2) ctx.closePath();
    ctx.strokeStyle = "#3367d6";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "rgba(51,103,214,0.2)";
    ctx.fill();
    for (const [x, y] of points) {
      ctx.beginPath();
      ctx.arc(x * canvas.width, y * canvas.height, 4, 0, 7);
      ctx.fillStyle = "#3367d6";
      ctx.fill();
    }
  }
}

async function saveZone() {
  if (points.length < 3) {
    msg("Нужно минимум 3 вершины", false);
    return;
  }
  const body = { zone_type: $("zoneType").value, polygon: points };
  try {
    await api(`/cameras/${current.id}/zones`, { method: "POST", body: JSON.stringify(body) });
    points = [];
    draw();
    loadZones();
    msg("Зона сохранена");
  } catch (e) {
    msg("Ошибка сохранения зоны: " + e.message, false);
  }
}

// ── Зоны ──

async function loadZones() {
  const tbody = $("zones").querySelector("tbody");
  tbody.innerHTML = "";
  try {
    const data = await api(`/cameras/${current.id}/zones`);
    zonePolys = data.items.map((z) => ({ type: z.zone_type, polygon: z.polygon }));
    draw();
    for (const z of data.items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${z.id}</td><td>${z.zone_type}</td><td>${z.polygon.length}</td>`;
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "danger";
      btn.onclick = () => deleteZone(z.id);
      td.appendChild(btn);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  } catch (e) {
    msg("Ошибка загрузки зон: " + e.message, false);
  }
}

async function deleteZone(id) {
  if (!window.confirm("Удалить зону? Покрытие и правила по ней перестанут считаться.")) return;
  try {
    await api(`/zones/${id}`, { method: "DELETE" });
    loadZones();
    msg("Зона удалена");
  } catch (e) {
    msg("Ошибка удаления: " + e.message, false);
  }
}

async function createCamera() {
  const body = {
    room: $("nc_room").value.trim(),
    name: $("nc_name").value.trim(),
    rtsp_url: $("nc_rtsp").value.trim(),
  };
  if (!body.room || !body.name || !body.rtsp_url) {
    msg("Заполните помещение, имя и rtsp_url", false);
    return;
  }
  try {
    const cam = await api("/cameras", { method: "POST", body: JSON.stringify(body) });
    $("nc_room").value = $("nc_name").value = $("nc_rtsp").value = "";
    $("addcam").open = false;
    await loadCameras();
    const created = cameras.find((c) => c.id === cam.id);
    if (created) selectCamera(created);
    msg("Камера заведена");
  } catch (e) {
    msg("Ошибка создания камеры: " + e.message, false);
  }
}

// ── Пороги датчиков ──

async function loadThresholds() {
  const tbody = $("thresholds").querySelector("tbody");
  tbody.innerHTML = "";
  try {
    const data = await api("/thresholds");
    for (const t of data.items) {
      const tr = document.createElement("tr");
      // textContent (не innerHTML): room — свободная строка оператора, иначе stored XSS.
      const cells = [
        t.room || "все",
        t.metric,
        t.op,
        String(t.value),
        t.severity + (t.enabled ? "" : " (выкл)"),
      ];
      for (const text of cells) {
        const cell = document.createElement("td");
        cell.textContent = text;
        tr.appendChild(cell);
      }
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "danger";
      btn.onclick = () => deleteThreshold(t.id);
      td.appendChild(btn);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  } catch (e) {
    msg("Ошибка загрузки порогов: " + e.message, false);
  }
}

async function createThreshold() {
  const value = parseFloat($("th_value").value);
  if (Number.isNaN(value)) {
    msg("Укажите числовое значение порога", false);
    return;
  }
  const body = {
    room: $("th_room").value.trim() || null,
    metric: $("th_metric").value,
    op: $("th_op").value,
    value,
    severity: $("th_sev").value,
  };
  try {
    await api("/thresholds", { method: "POST", body: JSON.stringify(body) });
    $("th_room").value = $("th_value").value = "";
    loadThresholds();
    msg("Порог добавлен");
  } catch (e) {
    msg("Ошибка добавления порога: " + e.message, false);
  }
}

async function deleteThreshold(id) {
  if (!window.confirm("Удалить порог? События по нему перестанут создаваться.")) return;
  try {
    await api(`/thresholds/${id}`, { method: "DELETE" });
    loadThresholds();
  } catch (e) {
    msg("Ошибка удаления порога: " + e.message, false);
  }
}

// ── Отчёт за период (#266) ──

async function downloadReportCsv() {
  const fromVal = $("rp_from").value;
  if (!fromVal) {
    msg("Укажите начало периода", false);
    return;
  }
  const params = new URLSearchParams({ from: new Date(fromVal).toISOString(), format: "csv" });
  const toVal = $("rp_to").value;
  if (toVal) params.set("to", new Date(toVal).toISOString());
  try {
    const resp = await fetch(`${API}/reports/sanitation?${params}`, { headers: headers(false) });
    if (!resp.ok) throw new Error(resp.status);
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (resp.headers.get("content-disposition") || "").match(/filename="(.+)"/)?.[1]
      || "sanitation-report.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 500);
    msg("Отчёт выгружен");
  } catch (e) {
    msg("Ошибка выгрузки отчёта: " + e.message, false);
  }
}

// ── Правила уборки (санитарный контроль, #265) ──

const ZONE_RU = { table: "стол", floor: "пол", window: "окно" };

async function loadCleaningRules() {
  const tbody = $("cleaningrules").querySelector("tbody");
  tbody.innerHTML = "";
  try {
    const data = await api("/cleaning-rules");
    for (const r of data.items) {
      const tr = document.createElement("tr");
      // textContent: room/zone_name — свободные строки оператора (без innerHTML).
      const cells = [
        r.room,
        ZONE_RU[r.zone_type] || r.zone_type,
        String(r.interval_hours),
        r.min_coverage_pct ? r.min_coverage_pct + "%" : "—",
        r.zone_name || "—",
        r.enabled ? "да" : "нет",
      ];
      for (const text of cells) {
        const cell = document.createElement("td");
        cell.textContent = text;
        tr.appendChild(cell);
      }
      const td = document.createElement("td");
      const toggle = document.createElement("button");
      toggle.textContent = r.enabled ? "выключить" : "включить";
      toggle.className = "sec";
      toggle.onclick = () => toggleCleaningRule(r.id, !r.enabled);
      td.appendChild(toggle);
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "danger";
      btn.onclick = () => deleteCleaningRule(r.id);
      td.appendChild(btn);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  } catch (e) {
    msg("Ошибка загрузки правил уборки: " + e.message, false);
  }
}

async function createCleaningRule() {
  const interval = parseFloat($("cr_interval").value);
  if (Number.isNaN(interval) || interval <= 0) {
    msg("Укажите интервал уборки в часах (> 0)", false);
    return;
  }
  const body = {
    room: $("cr_room").value.trim(),
    zone_type: $("cr_zone").value,
    interval_hours: interval,
    min_coverage_pct: parseInt($("cr_minpct").value, 10) || 0,
    zone_name: $("cr_name").value.trim() || null,
  };
  if (!body.room) {
    msg("Укажите помещение", false);
    return;
  }
  try {
    await api("/cleaning-rules", { method: "POST", body: JSON.stringify(body) });
    $("cr_room").value = $("cr_interval").value = $("cr_minpct").value = $("cr_name").value = "";
    loadCleaningRules();
    msg("Правило уборки добавлено");
  } catch (e) {
    msg("Ошибка добавления правила: " + e.message, false);
  }
}

async function toggleCleaningRule(id, enabled) {
  try {
    await api(`/cleaning-rules/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    loadCleaningRules();
  } catch (e) {
    msg("Ошибка изменения правила: " + e.message, false);
  }
}

async function deleteCleaningRule(id) {
  if (!window.confirm("Удалить правило уборки?")) return;
  try {
    await api(`/cleaning-rules/${id}`, { method: "DELETE" });
    loadCleaningRules();
  } catch (e) {
    msg("Ошибка удаления правила: " + e.message, false);
  }
}

// ── Контроль присутствия (рабочие зоны, #300/#312) ──

async function loadPresenceRules() {
  const tbody = $("presencerules").querySelector("tbody");
  tbody.innerHTML = "";
  try {
    const data = await api("/presence-rules");
    for (const r of data.items) {
      const tr = document.createElement("tr");
      // textContent: room — свободная строка оператора (без innerHTML).
      const cells = [
        r.room,
        r.window_start + "–" + r.window_end,
        String(r.max_absence_min),
        r.enabled ? "да" : "нет",
      ];
      for (const text of cells) {
        const cell = document.createElement("td");
        cell.textContent = text;
        tr.appendChild(cell);
      }
      const td = document.createElement("td");
      const toggle = document.createElement("button");
      toggle.textContent = r.enabled ? "выключить" : "включить";
      toggle.className = "sec";
      toggle.onclick = () => togglePresenceRule(r.id, !r.enabled);
      td.appendChild(toggle);
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "danger";
      btn.onclick = () => deletePresenceRule(r.id);
      td.appendChild(btn);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  } catch (e) {
    msg("Ошибка загрузки правил присутствия: " + e.message, false);
  }
}

async function createPresenceRule() {
  const body = {
    room: $("pr_room").value.trim(),
    window_start: $("pr_start").value,
    window_end: $("pr_end").value,
    max_absence_min: parseInt($("pr_maxabs").value, 10) || 30,
  };
  if (!body.room) {
    msg("Укажите помещение", false);
    return;
  }
  if (!body.window_start || !body.window_end || body.window_start >= body.window_end) {
    msg("Укажите дневное окно: начало раньше конца", false);
    return;
  }
  try {
    await api("/presence-rules", { method: "POST", body: JSON.stringify(body) });
    $("pr_room").value = $("pr_maxabs").value = "";
    loadPresenceRules();
    msg("Правило присутствия добавлено");
  } catch (e) {
    msg("Ошибка добавления правила: " + e.message, false);
  }
}

async function togglePresenceRule(id, enabled) {
  try {
    await api(`/presence-rules/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    loadPresenceRules();
  } catch (e) {
    msg("Ошибка изменения правила: " + e.message, false);
  }
}

async function deletePresenceRule(id) {
  if (!window.confirm("Удалить правило присутствия?")) return;
  try {
    await api(`/presence-rules/${id}`, { method: "DELETE" });
    loadPresenceRules();
  } catch (e) {
    msg("Ошибка удаления правила: " + e.message, false);
  }
}

// ── Расписания (таймер) ──

async function loadSchedules() {
  const tbody = $("schedules").querySelector("tbody");
  tbody.innerHTML = "";
  try {
    const data = await api("/schedules");
    for (const s of data.items) {
      const tr = document.createElement("tr");
      // textContent (не innerHTML): name/source_ref/room — свободные строки оператора.
      const cells = [
        s.name + (s.enabled ? "" : " (выкл)"),
        s.source_ref,
        s.room || "",
        String(s.interval_min),
      ];
      for (const text of cells) {
        const cell = document.createElement("td");
        cell.textContent = text;
        tr.appendChild(cell);
      }
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "danger";
      btn.onclick = () => deleteSchedule(s.id);
      td.appendChild(btn);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  } catch (e) {
    msg("Ошибка загрузки расписаний: " + e.message, false);
  }
}

async function createSchedule() {
  const interval = parseInt($("sc_interval").value, 10);
  const camId = $("sc_camera").value || null;
  const cam = camId ? cameras.find((c) => c.id === camId) : null;
  // Источник: из поля, иначе — поток выбранной камеры (go2rtc по имени).
  const sourceRef = $("sc_ref").value.trim() || (cam ? streamRef(cam) : "");
  const body = {
    name: $("sc_name").value.trim(),
    source_ref: sourceRef,
    room: $("sc_room").value.trim() || (cam ? cam.room : null),
    camera_id: camId, // нужен воркеру, чтобы взять ROI-зоны для % покрытия
    interval_min: interval,
  };
  if (!body.name || !body.source_ref || !(interval > 0)) {
    msg("Заполните имя, источник (или выберите камеру) и интервал (> 0)", false);
    return;
  }
  try {
    await api("/schedules", { method: "POST", body: JSON.stringify(body) });
    $("sc_name").value = $("sc_ref").value = $("sc_room").value = $("sc_interval").value = "";
    $("sc_camera").value = "";
    loadSchedules();
    msg("Расписание добавлено");
  } catch (e) {
    msg("Ошибка добавления расписания: " + e.message, false);
  }
}

async function deleteSchedule(id) {
  if (!window.confirm("Удалить расписание? Периодический анализ по нему остановится.")) return;
  try {
    await api(`/schedules/${id}`, { method: "DELETE" });
    loadSchedules();
  } catch (e) {
    msg("Ошибка удаления расписания: " + e.message, false);
  }
}

// ── Справочники: помещения и узлы датчиков ──

function fillRows(tableId, items, cols) {
  const tbody = $(tableId).querySelector("tbody");
  tbody.innerHTML = "";
  for (const it of items) {
    const tr = document.createElement("tr");
    for (const text of cols(it)) {
      const cell = document.createElement("td");
      cell.textContent = text; // textContent: значения вводит оператор
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }
}

async function loadRooms() {
  try {
    const data = await api("/rooms");
    fillRows("rooms", data.items, (r) => [r.id, r.name, r.is_cold ? "да" : ""]);
  } catch (e) {
    msg("Ошибка загрузки помещений: " + e.message, false);
  }
}

async function createRoom() {
  const body = {
    id: $("rm_id").value.trim(),
    name: $("rm_name").value.trim(),
    is_cold: $("rm_cold").checked,
  };
  if (!body.id || !body.name) {
    msg("Заполните id и название помещения", false);
    return;
  }
  try {
    await api("/rooms", { method: "POST", body: JSON.stringify(body) });
    $("rm_id").value = $("rm_name").value = "";
    $("rm_cold").checked = false;
    loadRooms();
    msg("Помещение добавлено");
  } catch (e) {
    msg("Ошибка добавления помещения: " + e.message, false);
  }
}

async function loadNodes() {
  try {
    const data = await api("/sensor-nodes");
    fillRows("nodes", data.items, (n) => [n.id, n.room_id, n.placement || ""]);
  } catch (e) {
    msg("Ошибка загрузки узлов: " + e.message, false);
  }
}

async function createNode() {
  const body = {
    id: $("nd_id").value.trim(),
    room_id: $("nd_room").value.trim(),
    placement: $("nd_place").value.trim() || null,
  };
  if (!body.id || !body.room_id) {
    msg("Заполните id узла и помещение", false);
    return;
  }
  try {
    await api("/sensor-nodes", { method: "POST", body: JSON.stringify(body) });
    $("nd_id").value = $("nd_room").value = $("nd_place").value = "";
    loadNodes();
    msg("Узел добавлен");
  } catch (e) {
    msg("Ошибка добавления узла: " + e.message, false);
  }
}

function loadAll() {
  loadLicense();
  loadAuraStatus();
  loadRooms();
  loadNodes();
  loadCameras();
  loadThresholds();
  loadCleaningRules();
  loadPresenceRules();
  loadSchedules();
}

$("reload").onclick = loadAll;
$("lickeyBtn").onclick = () => {
  const form = $("lickeyForm");
  form.hidden = !form.hidden;
  if (!form.hidden) $("lickey").focus();
};
$("lickeySave").onclick = () => applyLicenseKey($("lickey").value.trim());
$("lickeyClear").onclick = () => applyLicenseKey("");
$("aura_enabled").onchange = toggleAura;
$("rm_add").onclick = createRoom;
$("nd_add").onclick = createNode;
$("nc_save").onclick = createCamera;
$("saveCam").onclick = saveCamera;
$("deleteCam").onclick = deleteCamera;
$("runAnalysis").onclick = runAnalysisNow;
$("liveAnalysis").onclick = openLiveAnalysis;
$("loadFrame").onclick = loadFrame;
$("liveToggle").onclick = toggleLive;
$("videoToggle").onclick = toggleVideo;
$("saveZone").onclick = saveZone;
$("clearPoly").onclick = () => {
  points = [];
  draw();
};
$("th_add").onclick = createThreshold;
$("cr_add").onclick = createCleaningRule;
$("pr_add").onclick = createPresenceRule;
$("rp_csv").onclick = downloadReportCsv;
$("sc_add").onclick = createSchedule;

// ── Вкладки (#321): раздел в hash URL, последний открытый — в localStorage ──
const TABS = ["object", "cameras", "thresholds", "control", "schedules", "reports"];

function showTab(name) {
  if (!TABS.includes(name)) name = TABS[0];
  for (const t of TABS) {
    const panel = $("tab-" + t);
    if (panel) panel.hidden = t !== name;
    const btn = document.querySelector(`nav [data-tab="${t}"]`);
    if (btn) btn.classList.toggle("active", t === name);
  }
  localStorage.setItem("uiTab", name);
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
}

document.querySelectorAll("nav [data-tab]").forEach((b) => {
  b.onclick = () => showTab(b.dataset.tab);
});
window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));
showTab(location.hash.slice(1) || localStorage.getItem("uiTab") || "object");

if (keyInput.value) loadAll();
else setKeyState(false);
