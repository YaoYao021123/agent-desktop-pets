const CHARACTER_ORDER = ["kuma", "david", "Mao", "hugo"];
const STATES = [
  "sleep",
  "idle",
  "busy",
  "attention",
  "completed",
  "celebrate",
  "dizzy",
  "heart"
];

const STATE_LABELS = {
  sleep: "sleep",
  idle: "idle",
  busy: "busy",
  attention: "attention",
  completed: "jump",
  celebrate: "celebrate",
  dizzy: "dizzy",
  heart: "heart"
};

const SAMPLE_PACKETS = [
  { state: "busy", tokens: 159297887, primary: 98, secondary: 44 },
  { state: "completed", tokens: 159322014, primary: 71, secondary: 46 },
  { state: "attention", tokens: 159322014, primary: 64, secondary: 47 },
  { state: "idle", tokens: 159322014, primary: 29, secondary: 48 },
  { state: "heart", tokens: 159322014, primary: 33, secondary: 49 }
];

const els = {
  petSelect: document.querySelector("#petSelect"),
  viewSelect: document.querySelector("#viewSelect"),
  primaryInput: document.querySelector("#primaryInput"),
  secondaryInput: document.querySelector("#secondaryInput"),
  stateGrid: document.querySelector("#stateGrid"),
  jsonInput: document.querySelector("#jsonInput"),
  applyJson: document.querySelector("#applyJson"),
  sampleJson: document.querySelector("#sampleJson"),
  streamToggle: document.querySelector("#streamToggle"),
  message: document.querySelector("#message"),
  lcd: document.querySelector("#lcd"),
  deviceModel: document.querySelector("#deviceModel"),
  frontKeyHotspot: document.querySelector("#frontKeyHotspot"),
  key1Button: document.querySelector("#key1Button"),
  key2Button: document.querySelector("#key2Button"),
  powerButton: document.querySelector("#powerButton"),
  dashboardScreen: document.querySelector("#dashboardScreen"),
  creditsScreen: document.querySelector("#creditsScreen"),
  petSprite: document.querySelector("#petSprite"),
  petName: document.querySelector("#petName"),
  liveBadge: document.querySelector("#liveBadge"),
  primaryPct: document.querySelector("#primaryPct"),
  secondaryPct: document.querySelector("#secondaryPct"),
  primaryBar: document.querySelector("#primaryBar"),
  secondaryBar: document.querySelector("#secondaryBar"),
  primaryReset: document.querySelector("#primaryReset"),
  secondaryReset: document.querySelector("#secondaryReset"),
  stateChip: document.querySelector("#stateChip"),
  tokenText: document.querySelector("#tokenText")
};

const app = {
  manifests: new Map(),
  character: "kuma",
  state: "busy",
  view: "dashboard",
  live: true,
  primary: 98,
  secondary: 44,
  tokens: 159297887,
  primaryResetsAt: secondsFromNow(73 * 60),
  secondaryResetsAt: secondsFromNow((2 * 24 + 8) * 3600),
  streamTimer: null,
  sampleIndex: 0,
  idleFrame: 0,
  screenOff: false,
  hardwarePulseTimer: null
};

function secondsFromNow(delta) {
  return Math.floor(Date.now() / 1000) + delta;
}

function clampPct(value) {
  return Math.max(0, Math.min(100, Number(value) || 0));
}

function quotaRemainingPct(usedPct) {
  return 100 - clampPct(usedPct);
}

function quotaRemainingColor(remainingPct) {
  if (remainingPct >= 70) return "var(--green)";
  if (remainingPct >= 35) return "var(--orange)";
  return "var(--red)";
}

function resetColor(secondsLeft, windowLabel) {
  if (secondsLeft <= 0) return "var(--red)";
  if (windowLabel === "7d") {
    if (secondsLeft > 4 * 86400) return "var(--green)";
    if (secondsLeft > 2 * 86400) return "var(--orange)";
    return "var(--red)";
  }
  if (secondsLeft > 3 * 3600) return "var(--green)";
  if (secondsLeft > 3600) return "var(--orange)";
  return "var(--red)";
}

function resetText(resetAt, windowLabel) {
  if (!app.live || !resetAt) return { text: "resets --", color: "#8b949f" };
  const left = Math.max(0, resetAt - Math.floor(Date.now() / 1000));
  if (left === 0) return { text: "reset soon", color: "var(--red)" };

  let value;
  if (left >= 86400) {
    const days = Math.floor(left / 86400);
    const hours = String(Math.floor((left / 3600) % 24)).padStart(2, "0");
    value = `${days}d ${hours}h`;
  } else if (left >= 3600) {
    const hours = Math.floor(left / 3600);
    const mins = String(Math.floor((left / 60) % 60)).padStart(2, "0");
    value = `${hours}h ${mins}m`;
  } else {
    value = `${Math.floor(left / 60)}m`;
  }
  return { text: `resets in ${value}`, color: resetColor(left, windowLabel) };
}

function formatTokens(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value || 0);
}

function stateFile(manifest, state) {
  const file = manifest?.states?.[state] || manifest?.states?.idle;
  if (Array.isArray(file)) {
    app.idleFrame = (app.idleFrame + 1) % file.length;
    return file[app.idleFrame];
  }
  return file;
}

function assetPath(character, file) {
  return `../characters/${encodeURIComponent(character)}/${file}`;
}

async function loadManifest(character) {
  const response = await fetch(`../characters/${encodeURIComponent(character)}/manifest.json`, {
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`missing manifest for ${character}`);
  return response.json();
}

async function loadCharacters() {
  const available = [];
  for (const character of CHARACTER_ORDER) {
    try {
      const manifest = await loadManifest(character);
      app.manifests.set(character, manifest);
      available.push(character);
    } catch {
      // Keep the simulator tolerant while pets are being generated locally.
    }
  }

  if (!available.length) {
    els.petSelect.innerHTML = `<option>No character packs found</option>`;
    setMessage("No character packs found under characters/.");
    return;
  }

  if (!available.includes(app.character)) app.character = available[0];
  els.petSelect.innerHTML = available
    .map((name) => `<option value="${name}">${name}</option>`)
    .join("");
  els.petSelect.value = app.character;
}

function renderStateButtons() {
  els.stateGrid.innerHTML = STATES.map((state) => {
    const active = state === app.state ? " active" : "";
    return `<button class="${active}" type="button" data-state="${state}">${STATE_LABELS[state]}</button>`;
  }).join("");
}

function setMessage(text) {
  els.message.textContent = text;
}

function renderView() {
  const dashboard = app.view === "dashboard";
  els.dashboardScreen.hidden = !dashboard;
  els.creditsScreen.hidden = dashboard;
  els.viewSelect.value = app.view;
  els.lcd.classList.toggle("screen-off", app.screenOff);
}

function renderPet() {
  const manifest = app.manifests.get(app.character);
  if (!manifest) return;
  const file = stateFile(manifest, app.state);
  if (!file) return;
  els.petSprite.src = assetPath(app.character, file);
  els.petName.textContent = (manifest.name || app.character).toUpperCase();
  els.petSprite.alt = `${manifest.name || app.character} ${app.state} animation`;
}

function renderMeters() {
  const primaryReset = resetText(app.primaryResetsAt, "5h");
  const secondaryReset = resetText(app.secondaryResetsAt, "7d");
  const primaryRemaining = quotaRemainingPct(app.primary);
  const secondaryRemaining = quotaRemainingPct(app.secondary);

  els.liveBadge.textContent = app.live ? "LIVE" : "WAIT";
  els.liveBadge.style.color = app.live ? "var(--green)" : "var(--red)";
  els.primaryPct.textContent = `${primaryRemaining}%`;
  els.secondaryPct.textContent = `${secondaryRemaining}%`;
  els.primaryBar.style.width = `${primaryRemaining}%`;
  els.secondaryBar.style.width = `${secondaryRemaining}%`;
  els.primaryBar.style.background = quotaRemainingColor(primaryRemaining);
  els.secondaryBar.style.background = quotaRemainingColor(secondaryRemaining);
  els.primaryReset.textContent = primaryReset.text;
  els.secondaryReset.textContent = secondaryReset.text;
  els.primaryReset.style.color = primaryReset.color;
  els.secondaryReset.style.color = secondaryReset.color;
  els.stateChip.textContent = app.state;
  els.tokenText.textContent = formatTokens(app.tokens);
  els.primaryInput.value = app.primary;
  els.secondaryInput.value = app.secondary;
}

function render() {
  renderView();
  renderPet();
  renderMeters();
  renderStateButtons();
}

function pulseHardware(key) {
  els.deviceModel.dataset.activeKey = key;
  clearTimeout(app.hardwarePulseTimer);
  app.hardwarePulseTimer = setTimeout(() => {
    els.deviceModel.dataset.activeKey = "";
  }, 180);
}

function applyPacket(packet) {
  if (typeof packet !== "object" || packet === null || Array.isArray(packet)) {
    throw new Error("JSON must be an object");
  }
  if (packet.state && STATES.includes(packet.state)) app.state = packet.state;
  if (packet.tokens !== undefined) app.tokens = Number(packet.tokens) || 0;
  if (packet.primary !== undefined) app.primary = clampPct(packet.primary);
  if (packet.secondary !== undefined) app.secondary = clampPct(packet.secondary);
  if (packet.primary_resets_at !== undefined) app.primaryResetsAt = Number(packet.primary_resets_at) || 0;
  if (packet.secondary_resets_at !== undefined) app.secondaryResetsAt = Number(packet.secondary_resets_at) || 0;
  app.live = true;
  render();
}

function nextSample() {
  app.sampleIndex = (app.sampleIndex + 1) % SAMPLE_PACKETS.length;
  const packet = SAMPLE_PACKETS[app.sampleIndex];
  packet.primary_resets_at = secondsFromNow((40 + app.sampleIndex * 31) * 60);
  packet.secondary_resets_at = secondsFromNow((2 * 86400) + app.sampleIndex * 3700);
  els.jsonInput.value = JSON.stringify(packet);
  applyPacket(packet);
}

function pressKey1() {
  pulseHardware("key1");
  if (app.screenOff) {
    app.screenOff = false;
    setMessage("KEY1 woke the display.");
    render();
    return;
  }
  nextSample();
  setMessage("KEY1 advanced the bridge packet.");
}

function pressKey2() {
  pulseHardware("key2");
  if (app.screenOff) {
    app.screenOff = false;
    setMessage("KEY2 woke the display.");
    render();
    return;
  }
  app.view = app.view === "dashboard" ? "credits" : "dashboard";
  render();
  setMessage("KEY2 switched the screen.");
}

function pressPower() {
  pulseHardware("power");
  app.screenOff = !app.screenOff;
  render();
  setMessage(app.screenOff ? "Display off." : "Display on.");
}

function toggleStream() {
  if (app.streamTimer) {
    clearInterval(app.streamTimer);
    app.streamTimer = null;
    els.streamToggle.textContent = "Start stream";
    document.body.classList.remove("stream-on");
    setMessage("Stream paused.");
    return;
  }
  els.streamToggle.textContent = "Stop stream";
  document.body.classList.add("stream-on");
  setMessage("Stream running.");
  app.streamTimer = setInterval(nextSample, 2200);
  nextSample();
}

function bindEvents() {
  els.petSelect.addEventListener("change", () => {
    app.character = els.petSelect.value;
    render();
  });

  els.viewSelect.addEventListener("change", () => {
    app.view = els.viewSelect.value;
    render();
  });

  els.primaryInput.addEventListener("input", () => {
    app.primary = clampPct(els.primaryInput.value);
    render();
  });

  els.secondaryInput.addEventListener("input", () => {
    app.secondary = clampPct(els.secondaryInput.value);
    render();
  });

  els.stateGrid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-state]");
    if (!button) return;
    app.state = button.dataset.state;
    render();
  });

  els.applyJson.addEventListener("click", () => {
    try {
      applyPacket(JSON.parse(els.jsonInput.value));
      setMessage("Applied bridge packet.");
    } catch (error) {
      setMessage(error.message);
    }
  });

  els.sampleJson.addEventListener("click", nextSample);
  els.streamToggle.addEventListener("click", toggleStream);
  els.frontKeyHotspot.addEventListener("click", pressKey1);
  els.key1Button.addEventListener("click", pressKey1);
  els.key2Button.addEventListener("click", pressKey2);
  els.powerButton.addEventListener("click", pressPower);
}

async function init() {
  renderStateButtons();
  bindEvents();
  await loadCharacters();
  render();
  setInterval(() => renderMeters(), 30_000);
  setInterval(() => {
    if (app.state === "idle") renderPet();
  }, 1600);
}

init();
