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

$("reload").onclick = loadCameras;
$("saveCam").onclick = saveCamera;
$("loadFrame").onclick = loadFrame;
$("saveZone").onclick = saveZone;
$("clearPoly").onclick = () => {
  points = [];
  draw();
};

if (keyInput.value) loadCameras();
