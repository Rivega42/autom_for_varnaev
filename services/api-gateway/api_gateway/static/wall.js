// Логика дашборда «Стена роликов» (#wall). См. wall.html.
//
// Слева — сетка роликов. По кнопке «▶ Живой анализ» ролик запускается через
// НАШ браузерный движок (mountLiveAnalysis): скелет, заливка «протёртости» и
// индикатор халата рисуются ПРЯМО НА ВИДЕО (как в PoC «над камерой»), а события
// (действие/покрытие %/халат) со стоп-кадрами уходят в журнал → лента справа.
// Кнопка «сервер» — полный серверный прогон ролика (file-задание воркеру).
// Справа — лента событий + кадров-улик (опрос раз в 3 c).

import { mountLiveAnalysis } from "/ui/live-embed.mjs";

const API = "/api/v1";

const keyInput = document.getElementById("apikey");
keyInput.value = localStorage.getItem("apiKey") || "";
const apiKey = () => keyInput.value.trim();

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-API-Key": apiKey() }, opts.headers || {});
  if (opts.body) headers["Content-Type"] = "application/json";
  const resp = await fetch(API + path, { ...opts, headers });
  let body = {};
  try { body = await resp.json(); } catch { /* пустой ответ */ }
  if (!resp.ok) throw new Error((body.error && body.error.message) || ("HTTP " + resp.status));
  return body.data !== undefined ? body.data : body;
}

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// === Сетка роликов ===========================================================
async function loadClips() {
  const grid = document.getElementById("clipGrid");
  const hint = document.getElementById("clipsHint");
  if (!apiKey()) { hint.textContent = "Введите X-API-Key справа сверху."; return; }
  hint.textContent = "Загрузка роликов…";
  let data;
  try { data = await api("/clips"); }
  catch (e) { hint.textContent = "Ошибка: " + e.message; return; }
  const clips = data.clips || [];
  grid.replaceChildren();
  if (!clips.length) {
    hint.textContent = "Роликов нет. Каталог: " + (data.dir || "?") +
      " (положите *.mp4 в samples/ и нажмите «Обновить ролики»).";
    return;
  }
  hint.textContent = clips.length +
    " роликов. «▶ Живой анализ» рисует скелет/халат на видео. Для протирания — " +
    "обязательно обведи стол кнопкой «✎ Обвести стол (ROI)» (иначе протирание ложит).";
  clips.forEach((clip) => grid.append(renderClip(clip)));
}

function renderClip(clip) {
  const card = el("div", "card");
  card.append(el("h3", null, clip.name));

  // Хост: до старта — превью-видео; по кнопке его заменяет живой анализ.
  const host = el("div");
  const preview = el("video");
  preview.src = clip.url; preview.controls = true; preview.muted = true;
  preview.playsInline = true; preview.style.cssText = "display:block;width:100%";
  host.append(preview);
  card.append(host);

  // Тумблеры «что распознаём» под каждой «камерой» (инициализируем из сохранённых
  // флагов камеры, по умолчанию всё включено). Объект мутируется на лету — живой
  // анализ читает его каждый кадр, поэтому переключение действует сразу.
  const a = clip.analytics || {};
  const features = {
    uniform: a.uniform !== false, wipe: a.coverage !== false,
    actions: a.actions !== false, poses: a.pose !== false,
  };
  const featRow = el("div", "tools");
  [["uniform", "Халат"], ["wipe", "Протирание"], ["actions", "Действия"], ["poses", "Позы"]]
    .forEach(([key, label]) => {
      const b = el("button", features[key] ? "on" : "", label);
      b.title = "Распознавать: " + label;
      b.addEventListener("click", () => {
        features[key] = !features[key];
        b.classList.toggle("on", features[key]);
        // Сохраняем в камеру (чтобы серверный прогон и перезагрузка их учли).
        api("/cameras/" + clip.camera_id, {
          method: "PATCH",
          body: JSON.stringify({ analytics: { pose: features.poses, actions: features.actions,
            uniform: features.uniform, coverage: features.wipe } }),
        }).catch(() => {});
      });
      featRow.append(b);
    });
  card.append(featRow);

  const tools = el("div", "tools");
  const status = el("div", "status");

  // Живой браузерный анализ ПРЯМО НА ВИДЕО (скелет/стол/халат).
  const liveBtn = el("button", "primary", "▶ Живой анализ (скелет/стол/халат)");
  liveBtn.addEventListener("click", () => {
    liveBtn.disabled = true; liveBtn.textContent = "анализ идёт ▸ см. видео и ленту";
    status.textContent = "⚠️ Нажми «✎ Обвести стол (ROI)» в плеере и обведи стол — " +
      "иначе «протирание» считается по всему кадру (бывает ложно).";
    mountLiveAnalysis(host, {            // заменяет превью на живой компонент
      clipUrl: clip.url, zones: clip.zones, room: null,
      cameraId: clip.camera_id, apiKey: apiKey(), features,
    });
  });

  // Полный серверный прогон ролика (file-задание воркеру) — с опросом статуса.
  const srvBtn = el("button", "", "сервер (полный прогон)");
  srvBtn.addEventListener("click", async () => {
    srvBtn.disabled = true; status.textContent = "⏳ Отправляю ролик на сервер…";
    try {
      const task = await api("/analysis-tasks", {
        method: "POST",
        body: JSON.stringify({ source_type: "file", source_ref: clip.url,
          camera_id: clip.camera_id, pipeline: "pose_v1" }),
      });
      let done = false;
      for (let i = 0; i < 120 && !done; i++) {
        await sleep(1500);
        const t = await api("/analysis-tasks/" + task.id).catch(() => null);
        if (!t) continue;
        if (t.status === "done") { status.textContent = "✓ Серверный анализ завершён — лента справа →"; done = true; }
        else if (t.status === "failed") { status.textContent = "✗ Ошибка: " + String(t.error || "").slice(0, 90); done = true; }
        else status.textContent = t.status === "queued" ? "⏳ В очереди…" : "⏳ Анализирую на сервере…";
      }
    } catch (e) { status.textContent = "Ошибка: " + e.message; }
    srvBtn.disabled = false;
  });

  // Удалить ролик «из стены»: файл + мягкое удаление «камеры»-ролика.
  const delBtn = el("button", "", "🗑 Удалить");
  delBtn.title = "Удалить ролик из стены (файл + камера)";
  delBtn.addEventListener("click", async () => {
    if (!window.confirm("Удалить ролик «" + clip.name + "» из стены?")) return;
    try {
      await api("/clips/" + encodeURIComponent(clip.file), { method: "DELETE" });
      await loadClips();
    } catch (e) { status.textContent = "Ошибка удаления: " + e.message; }
  });

  tools.append(liveBtn, srvBtn, delBtn);
  card.append(tools, status);
  return card;
}

// === Лента событий + кадров-улик ============================================
function renderEvent(ev) {
  const item = el("div", "ev");
  const row = el("div", "row");
  row.append(el("time", null, new Date(ev.ts).toLocaleTimeString("ru-RU")));
  row.append(el("span", "sev " + (ev.severity || "info"), ev.severity || "info"));
  item.append(row);
  item.append(el("div", "msg", ev.message || ev.type || "—"));
  const meta = [ev.type, ev.room].filter(Boolean).join(" · ");
  if (meta) item.append(el("div", "meta", meta));
  const url = (ev.payload && ev.payload.artifact_url) || ev.artifact_url;
  if (url) {
    const img = el("img");
    img.src = url + (url.includes("?") ? "&" : "?") + "api_key=" + encodeURIComponent(apiKey());
    img.addEventListener("click", () => window.open(img.src, "_blank"));
    item.append(img);
  }
  return item;
}

function renderArtifact(a) {
  const item = el("div", "ev");
  const row = el("div", "row");
  row.append(el("time", null, new Date(a.created_at).toLocaleTimeString("ru-RU")));
  row.append(el("span", "sev info", "кадр-улика"));
  item.append(row);
  const img = el("img");
  img.src = a.url + "?api_key=" + encodeURIComponent(apiKey());
  img.addEventListener("click", () => window.open(img.src, "_blank"));
  item.append(img);
  return item;
}

async function pollFeed() {
  const list = document.getElementById("feedList");
  if (apiKey()) {
    try {
      const [evData, artData] = await Promise.all([
        api("/events?limit=60"),
        api("/artifacts?limit=40").catch(() => ({ artifacts: [] })),
      ]);
      const events = Array.isArray(evData) ? evData : (evData.events || evData.items || []);
      const arts = (artData.artifacts || []);
      const merged = [
        ...events.map((e) => ({ ts: e.ts, node: () => renderEvent(e) })),
        ...arts.map((a) => ({ ts: a.created_at, node: () => renderArtifact(a) })),
      ].sort((x, y) => new Date(y.ts) - new Date(x.ts));
      list.replaceChildren(...merged.map((m) => m.node()));
    } catch (e) {
      if (!list.children.length) list.append(el("div", "hint", "Лента: " + e.message));
    }
  }
  setTimeout(pollFeed, 3000);
}

// === Загрузка ролика =========================================================
async function uploadClip(file) {
  const hint = document.getElementById("clipsHint");
  hint.textContent = "Загрузка «" + file.name + "» (" + Math.round(file.size / 1e6) + " МБ)…";
  try {
    const resp = await fetch(API + "/clips/upload?name=" + encodeURIComponent(file.name), {
      method: "POST", headers: { "X-API-Key": apiKey() }, body: file,
    });
    if (!resp.ok) {
      let m = "HTTP " + resp.status;
      try { m = (await resp.json()).error.message || m; } catch { /* нет тела */ }
      throw new Error(m);
    }
    await loadClips();
  } catch (e) { hint.textContent = "Ошибка загрузки: " + e.message; }
}

// === Старт ===================================================================
const uploadInput = document.getElementById("uploadInput");
document.getElementById("uploadBtn").addEventListener("click", () => {
  if (!apiKey()) { document.getElementById("clipsHint").textContent = "Сначала введите X-API-Key."; return; }
  uploadInput.click();
});
uploadInput.addEventListener("change", () => {
  if (uploadInput.files[0]) uploadClip(uploadInput.files[0]);
  uploadInput.value = "";
});
keyInput.addEventListener("change", () => {
  localStorage.setItem("apiKey", apiKey());
  loadClips();
});
document.getElementById("reload").addEventListener("click", loadClips);
loadClips();
pollFeed();
