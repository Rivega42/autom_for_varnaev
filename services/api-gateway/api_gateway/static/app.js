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

const keyInput = $("apikey");
keyInput.value = localStorage.getItem("apiKey") || "";
keyInput.addEventListener("change", () => localStorage.setItem("apiKey", keyInput.value));

function msg(text, ok = true) {
  const el = $("msg");
  el.textContent = text;
  el.style.color = ok ? "#cdf" : "#ffd0d0";
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

// ── Камеры ──

async function loadCameras() {
  try {
    const data = await api("/cameras");
    cameras = data.items;
    renderCamList();
    msg(`Камер: ${cameras.length}`);
  } catch (e) {
    msg("Ошибка загрузки камер: " + e.message, false);
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

const canvas = $("canvas");
const ctx = canvas.getContext("2d");

canvas.addEventListener("click", (ev) => {
  const r = canvas.getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width;
  const y = (ev.clientY - r.top) / r.height;
  points.push([Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]);
  draw();
});

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (frameImg) ctx.drawImage(frameImg, 0, 0, canvas.width, canvas.height);
  else {
    ctx.fillStyle = "#eee";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
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
    for (const z of data.items) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${z.id}</td><td>${z.zone_type}</td><td>${z.polygon.length}</td>`;
      const td = document.createElement("td");
      const btn = document.createElement("button");
      btn.textContent = "удалить";
      btn.className = "sec";
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
      btn.className = "sec";
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
  try {
    await api(`/thresholds/${id}`, { method: "DELETE" });
    loadThresholds();
  } catch (e) {
    msg("Ошибка удаления порога: " + e.message, false);
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
      btn.className = "sec";
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
  const body = {
    name: $("sc_name").value.trim(),
    source_ref: $("sc_ref").value.trim(),
    room: $("sc_room").value.trim() || null,
    interval_min: interval,
  };
  if (!body.name || !body.source_ref || !(interval > 0)) {
    msg("Заполните имя, источник и интервал (> 0)", false);
    return;
  }
  try {
    await api("/schedules", { method: "POST", body: JSON.stringify(body) });
    $("sc_name").value = $("sc_ref").value = $("sc_room").value = $("sc_interval").value = "";
    loadSchedules();
    msg("Расписание добавлено");
  } catch (e) {
    msg("Ошибка добавления расписания: " + e.message, false);
  }
}

async function deleteSchedule(id) {
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
  loadRooms();
  loadNodes();
  loadCameras();
  loadThresholds();
  loadSchedules();
}

$("reload").onclick = loadAll;
$("rm_add").onclick = createRoom;
$("nd_add").onclick = createNode;
$("nc_save").onclick = createCamera;
$("saveCam").onclick = saveCamera;
$("loadFrame").onclick = loadFrame;
$("saveZone").onclick = saveZone;
$("clearPoly").onclick = () => {
  points = [];
  draw();
};
$("th_add").onclick = createThreshold;
$("sc_add").onclick = createSchedule;

if (keyInput.value) loadAll();
