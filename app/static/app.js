const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteLabel = (n) => `${NOTE_NAMES[n % 12]}${Math.floor(n / 12) - 1}`;

const padsEl = document.getElementById("pads");
const midiNameEl = document.getElementById("midi-name");
const midiDotEl = document.getElementById("midi-dot");
const sampleCountEl = document.getElementById("sample-count");
const cooldownEl = document.getElementById("cooldown");
const cooldownOutEl = document.getElementById("cooldown-out");
const fadeMsEl = document.getElementById("fade-ms");
const fadeMsOutEl = document.getElementById("fade-ms-out");
const maxPlayEl = document.getElementById("max-play");
const maxPlayOutEl = document.getElementById("max-play-out");
const stopAllBtn = document.getElementById("stop-all");

let GROUPS = [];
let SAMPLES_BY_GROUP = {};

const fmtSec = (s) => `${Number(s).toFixed(1)} s`;
const fmtSecInt = (s) => `${Math.round(Number(s))} s`;
const fmtMsAsSec = (ms) => `${(Number(ms) / 1000).toFixed(1)} s`;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

async function refreshStatus() {
  try {
    const s = await fetchJSON("/api/status");
    midiNameEl.textContent = s.midi_port || "TouchMe não conectada";
    midiDotEl.classList.toggle("live", !!s.midi_port);
    sampleCountEl.textContent = `${s.sample_count} samples · ${s.groups.length} grupos`;
    // update "tocando agora" labels
    for (const [n, lp] of Object.entries(s.last_plays || {})) {
      const el = document.querySelector(`.pad[data-note="${n}"] .pad-now`);
      if (el) {
        const recent = lp && (Date.now() / 1000 - lp.at < 30);
        el.textContent = lp ? lp.sample : "—";
        el.classList.toggle("recent", !!recent);
      }
    }
  } catch (e) { /* ignore */ }
}

function buildPad(note, padCfg) {
  const wrap = document.createElement("div");
  wrap.className = "pad";
  wrap.dataset.note = note;

  const head = document.createElement("div");
  head.className = "pad-head";
  head.innerHTML = `<span class="pad-name">${noteLabel(note)}</span><span class="pad-num">note ${note}</span>`;
  wrap.appendChild(head);

  // Group dropdown
  const select = document.createElement("select");
  select.appendChild(new Option("— sem grupo —", ""));
  for (const g of GROUPS) {
    const count = (SAMPLES_BY_GROUP[g] || []).length;
    select.appendChild(new Option(`${g}  ·  ${count} sons`, g));
  }
  select.value = padCfg.group || "";
  wrap.appendChild(select);

  // "Tocando agora" line
  const nowRow = document.createElement("div");
  nowRow.className = "pad-row pad-now-row";
  const nowLbl = document.createElement("span");
  nowLbl.className = "pad-now-lbl";
  nowLbl.textContent = "tocando agora:";
  const now = document.createElement("span");
  now.className = "pad-now";
  now.textContent = padCfg.last_play ? padCfg.last_play.sample : "—";
  nowRow.append(nowLbl, now);
  wrap.appendChild(nowRow);

  // Volume
  const volRow = document.createElement("div");
  volRow.className = "pad-row";
  const vol = document.createElement("input");
  vol.type = "range"; vol.min = 0; vol.max = 1; vol.step = 0.01;
  vol.value = padCfg.volume ?? 1;
  vol.style.flex = "1";
  const volOut = document.createElement("output");
  volOut.textContent = `${Math.round((padCfg.volume ?? 1) * 100)}%`;
  volRow.appendChild(Object.assign(document.createElement("span"), { textContent: "vol" }));
  volRow.appendChild(vol);
  volRow.appendChild(volOut);
  wrap.appendChild(volRow);

  // Hold
  const holdRow = document.createElement("div");
  holdRow.className = "pad-row";
  const hold = document.createElement("input");
  hold.type = "checkbox"; hold.checked = padCfg.hold !== false;
  const holdLabel = document.createElement("label");
  holdLabel.append(hold, " segurar = continua tocando");
  holdRow.appendChild(holdLabel);
  wrap.appendChild(holdRow);

  // Actions
  const actions = document.createElement("div");
  actions.className = "pad-actions";
  const testBtn = document.createElement("button");
  testBtn.textContent = "▶ testar (random do grupo)";
  actions.appendChild(testBtn);
  wrap.appendChild(actions);

  // wiring
  const save = (patch) => fetchJSON(`/api/pad/${note}`, {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify(patch),
  });

  select.addEventListener("change", () => save({ group: select.value || null }));
  vol.addEventListener("input", () => { volOut.textContent = `${Math.round(vol.value * 100)}%`; });
  vol.addEventListener("change", () => save({ volume: parseFloat(vol.value) }));
  hold.addEventListener("change", () => save({ hold: hold.checked }));
  testBtn.addEventListener("click", async () => {
    wrap.classList.add("active");
    const res = await fetchJSON(`/api/test/${note}`, { method: "POST" });
    if (res?.last_play) {
      now.textContent = res.last_play.sample;
      now.classList.add("recent");
    }
    setTimeout(() => { wrap.classList.remove("active"); now.classList.remove("recent"); }, 600);
  });

  return wrap;
}

async function init() {
  const [config, gRes] = await Promise.all([
    fetchJSON("/api/config"),
    fetchJSON("/api/groups"),
  ]);
  GROUPS = gRes.groups;
  SAMPLES_BY_GROUP = gRes.samples_by_group;

  cooldownEl.value = config.retrigger_cooldown_seconds ?? 2;
  cooldownOutEl.textContent = fmtSec(cooldownEl.value);
  fadeMsEl.value = config.release_fade_ms ?? 5000;
  fadeMsOutEl.textContent = fmtMsAsSec(fadeMsEl.value);
  maxPlayEl.value = config.max_play_seconds ?? 20;
  maxPlayOutEl.textContent = fmtSecInt(maxPlayEl.value);

  padsEl.innerHTML = "";
  const notes = Object.keys(config.pads).map(Number).sort((a, b) => a - b);
  for (const n of notes) padsEl.appendChild(buildPad(n, config.pads[n]));

  refreshStatus();
  setInterval(refreshStatus, 1500);
}

function postGlobal(key, value) {
  return fetchJSON("/api/global", {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({ [key]: value }),
  });
}

cooldownEl.addEventListener("input", () => { cooldownOutEl.textContent = fmtSec(cooldownEl.value); });
cooldownEl.addEventListener("change", () => postGlobal("retrigger_cooldown_seconds", parseFloat(cooldownEl.value)));
fadeMsEl.addEventListener("input", () => { fadeMsOutEl.textContent = fmtMsAsSec(fadeMsEl.value); });
fadeMsEl.addEventListener("change", () => postGlobal("release_fade_ms", parseFloat(fadeMsEl.value)));
maxPlayEl.addEventListener("input", () => { maxPlayOutEl.textContent = fmtSecInt(maxPlayEl.value); });
maxPlayEl.addEventListener("change", () => postGlobal("max_play_seconds", parseFloat(maxPlayEl.value)));
stopAllBtn.addEventListener("click", () => fetchJSON("/api/stop", { method: "POST" }));

document.getElementById("shuffle-groups").addEventListener("click", async () => {
  if (!confirm("Embaralhar grupos entre os 12 pads? A configuração atual será substituída.")) return;
  await fetchJSON("/api/shuffle", { method: "POST" });
  init();
});

// ── Presets ────────────────────────────────────────────────────────────
const presetsListEl = document.getElementById("presets-list");

async function refreshPresets() {
  try {
    const { presets } = await fetchJSON("/api/presets");
    presetsListEl.innerHTML = "";
    if (!presets.length) {
      presetsListEl.innerHTML = `<p class="presets-empty">Nenhuma configuração salva ainda. Ajuste os sliders acima e clique em <em>Salvar configurações</em>.</p>`;
      return;
    }
    for (const p of presets) {
      const card = document.createElement("div");
      card.className = "preset";
      const v = p.values || {};
      card.innerHTML = `
        <div class="preset-head">
          <span class="preset-name">${p.name}</span>
          <span class="preset-meta">${new Date(p.saved_at * 1000).toLocaleString("pt-BR")}</span>
        </div>
        <div class="preset-values">
          <span>lockout <strong>${(v.retrigger_cooldown_seconds ?? 0).toFixed(1)}s</strong></span>
          <span>fade <strong>${((v.release_fade_ms ?? 0) / 1000).toFixed(1)}s</strong></span>
          <span>max <strong>${Math.round(v.max_play_seconds ?? 0)}s</strong></span>
        </div>
        <div class="preset-actions">
          <button class="primary load-btn">aplicar</button>
          <button class="danger delete-btn">remover</button>
        </div>`;
      card.querySelector(".load-btn").addEventListener("click", async () => {
        await fetchJSON(`/api/presets/${encodeURIComponent(p.name)}/load`, { method: "POST" });
        init();
      });
      card.querySelector(".delete-btn").addEventListener("click", async () => {
        if (!confirm(`Remover "${p.name}"?`)) return;
        await fetchJSON(`/api/presets/${encodeURIComponent(p.name)}`, { method: "DELETE" });
        refreshPresets();
      });
      presetsListEl.appendChild(card);
    }
  } catch (e) { /* ignore */ }
}

document.getElementById("save-preset").addEventListener("click", async () => {
  const res = await fetchJSON("/api/presets", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  });
  if (res?.preset?.name) {
    // small visual ping
    const btn = document.getElementById("save-preset");
    const orig = btn.textContent;
    btn.textContent = `✓ salvo como ${res.preset.name}`;
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }
  refreshPresets();
});

refreshPresets();

init().catch(e => {
  padsEl.innerHTML = `<p style="color:#c8654c">Erro ao carregar: ${e.message}</p>`;
});
