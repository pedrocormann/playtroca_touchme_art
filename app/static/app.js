const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function noteLabel(n) {
  return `${NOTE_NAMES[n % 12]}${Math.floor(n / 12) - 1}`;
}

const padsEl = document.getElementById("pads");
const midiNameEl = document.getElementById("midi-name");
const midiDotEl = document.getElementById("midi-dot");
const sampleCountEl = document.getElementById("sample-count");
const masterEl = document.getElementById("master-volume");
const masterOutEl = document.getElementById("master-volume-out");
const cooldownEl = document.getElementById("cooldown");
const cooldownOutEl = document.getElementById("cooldown-out");
const fadeMsEl = document.getElementById("fade-ms");
const fadeMsOutEl = document.getElementById("fade-ms-out");
const maxPlayEl = document.getElementById("max-play");
const maxPlayOutEl = document.getElementById("max-play-out");
const stopAllBtn = document.getElementById("stop-all");

let SAMPLES = [];

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
    if (s.midi_port) {
      midiNameEl.textContent = s.midi_port;
      midiDotEl.classList.add("live");
    } else {
      midiNameEl.textContent = "TouchMe não conectada";
      midiDotEl.classList.remove("live");
    }
    sampleCountEl.textContent = s.sample_count;
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

  const select = document.createElement("select");
  const optNone = new Option("— sem som —", "");
  select.appendChild(optNone);
  for (const s of SAMPLES) select.appendChild(new Option(s, s));
  select.value = padCfg.file || "";
  wrap.appendChild(select);

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

  const holdRow = document.createElement("div");
  holdRow.className = "pad-row";
  const hold = document.createElement("input");
  hold.type = "checkbox"; hold.checked = padCfg.hold !== false;
  const holdLabel = document.createElement("label");
  holdLabel.append(hold, " segurar = continua tocando");
  holdRow.appendChild(holdLabel);
  wrap.appendChild(holdRow);

  const actions = document.createElement("div");
  actions.className = "pad-actions";
  const testBtn = document.createElement("button");
  testBtn.textContent = "▶ testar";
  actions.appendChild(testBtn);
  wrap.appendChild(actions);

  // wiring
  const save = (patch) => fetchJSON(`/api/pad/${note}`, {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify(patch),
  });

  select.addEventListener("change", () => save({ file: select.value || null }));
  vol.addEventListener("input", () => {
    volOut.textContent = `${Math.round(vol.value * 100)}%`;
  });
  vol.addEventListener("change", () => save({ volume: parseFloat(vol.value) }));
  hold.addEventListener("change", () => save({ hold: hold.checked }));
  testBtn.addEventListener("click", async () => {
    wrap.classList.add("active");
    await fetchJSON(`/api/test/${note}`, { method: "POST" });
    setTimeout(() => wrap.classList.remove("active"), 300);
  });

  return wrap;
}

async function init() {
  const [config, samplesRes] = await Promise.all([
    fetchJSON("/api/config"),
    fetchJSON("/api/samples"),
  ]);
  SAMPLES = samplesRes.samples;
  masterEl.value = config.master_volume ?? 1;
  masterOutEl.textContent = `${Math.round((config.master_volume ?? 1) * 100)}%`;
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
  setInterval(refreshStatus, 3000);
}

function postGlobal(key, value) {
  return fetchJSON("/api/global", {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({ [key]: value }),
  });
}

masterEl.addEventListener("input", () => {
  masterOutEl.textContent = `${Math.round(masterEl.value * 100)}%`;
});
masterEl.addEventListener("change", () => postGlobal("master_volume", parseFloat(masterEl.value)));

cooldownEl.addEventListener("input", () => { cooldownOutEl.textContent = fmtSec(cooldownEl.value); });
cooldownEl.addEventListener("change", () => postGlobal("retrigger_cooldown_seconds", parseFloat(cooldownEl.value)));

fadeMsEl.addEventListener("input", () => { fadeMsOutEl.textContent = fmtMsAsSec(fadeMsEl.value); });
fadeMsEl.addEventListener("change", () => postGlobal("release_fade_ms", parseFloat(fadeMsEl.value)));

maxPlayEl.addEventListener("input", () => { maxPlayOutEl.textContent = fmtSecInt(maxPlayEl.value); });
maxPlayEl.addEventListener("change", () => postGlobal("max_play_seconds", parseFloat(maxPlayEl.value)));

stopAllBtn.addEventListener("click", () => fetchJSON("/api/stop", { method: "POST" }));

init().catch(e => {
  padsEl.innerHTML = `<p style="color:#c8654c">Erro ao carregar: ${e.message}</p>`;
});
