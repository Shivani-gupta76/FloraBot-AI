import { api, ApiError } from "/js/api.js";

const HARDWARE_INTERVAL_MS = 1000;
const COMMANDS_INTERVAL_MS = 2000;
const COMMAND_LIMIT = 20;
const TICK_MS = 250;
const SLIDER_DEBOUNCE_MS = 300;
const SLIDER_MAX_SECONDS = 10;
const HIGHLIGHT_MS = 4000;
const FLASH_MS = 5000;
const TOAST_MS = 6000;
const RECENT_MS = 15000;

const OPEN_STATUSES = new Set(["PENDING", "DELIVERED"]);
const DELAYED_BEHAVIOURS = new Set(["AUTO", "FAILING"]);
const STATUS_INFO = {
  PENDING: { label: "Pending", tone: "sun" },
  DELIVERED: { label: "Received", tone: "sun" },
  ACKNOWLEDGED: { label: "Confirmed", tone: "leaf" },
  FAILED: { label: "Failed", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "danger" },
  SUPERSEDED: { label: "Replaced", tone: "muted" },
};
const THEMES = ["auto", "light", "dark"];
const THEME_NAMES = { auto: "Auto", light: "Light", dark: "Dark" };

const $ = (id) => document.getElementById(id);

const ui = {
  modeBadge: $("mode-badge"),
  themeToggle: $("theme-toggle"),
  themeName: $("theme-name"),
  themeIcons: document.querySelectorAll("[data-theme-icon]"),
  unreachableBanner: $("unreachable-banner"),
  unreachableDetail: $("unreachable-detail"),
  realBanner: $("real-banner"),
  board: $("board"),
  ledCaption: $("led-caption"),
  boardNote: $("board-note"),
  factDevice: $("fact-device"),
  factDot: $("fact-dot"),
  factConnection: $("fact-connection"),
  factSeen: $("fact-seen"),
  factLed: $("fact-led"),
  factLedSub: $("fact-led-sub"),
  factMode: $("fact-mode"),
  factModeSub: $("fact-mode-sub"),
  commandPanel: $("command-panel"),
  commandTitle: $("command-title"),
  commandStatus: $("command-status"),
  flashRegion: $("flash-region"),
  commandEmpty: $("command-empty"),
  commandPending: $("command-pending"),
  commandState: $("command-state"),
  countdownTrack: $("countdown-track"),
  countdownBar: $("countdown-bar"),
  countdownText: $("countdown-text"),
  stepRequested: $("step-requested"),
  stepCollect: $("step-collect"),
  stepCollectTitle: $("step-collect-title"),
  stepCollectDetail: $("step-collect-detail"),
  stepConfirm: $("step-confirm"),
  commandNote: $("command-note"),
  manualActions: $("manual-actions"),
  ackConfirm: $("ack-confirm"),
  ackFail: $("ack-fail"),
  simPanel: $("sim-panel"),
  behaviourInputs: [...document.querySelectorAll('input[name="behaviour"]')],
  delayField: $("delay-field"),
  delay: $("delay"),
  delayValue: $("delay-value"),
  logEmpty: $("log-empty"),
  logList: $("log-list"),
  toasts: $("toasts"),
  announcer: $("announcer"),
};

const state = {
  hardware: null,
  hardwareStamp: 0,
  hardwareError: null,
  commandsError: null,
  wasUnreachable: false,
  ackSending: null,
  ackedCommandId: null,
};

// Every request gets a stamp so a slow poll that started before a settings change cannot overwrite its result.
let requestStamp = 0;

const simulation = { behaviour: null, delay: 0, debounceTimer: null, sending: false, queued: null };
const log = { rows: new Map(), statuses: new Map(), flashed: new Set(), primed: false };
let flashTimer = null;

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setAttr(node, name, value) {
  if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

function parseTime(value) {
  if (typeof value !== "string") return null;
  // The server sends microseconds; trim to milliseconds and treat a missing zone as UTC so every browser parses it.
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
  const time = Date.parse(match ? `${match[1]}${(match[2] ?? "").slice(0, 4)}${match[3] ?? "Z"}` : value);
  return Number.isNaN(time) ? null : time;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function clockTime(time) {
  if (time === null) return "--:--:--";
  const date = new Date(time);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function formatNumber(value) {
  return String(Math.round(value * 100) / 100);
}

function timeAgo(time) {
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000));
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `on ${new Date(time).toLocaleDateString()}`;
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function isDummy(hardware) {
  return hardware?.mode === "dummy";
}

function deviceName(hardware) {
  return isDummy(hardware) ? "the simulated ESP32" : "the ESP32";
}

function statusInfo(status) {
  return STATUS_INFO[status] ?? { label: String(status), tone: "muted" };
}

function errorMessage(error) {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

function icon(name) {
  return $(`icon-${name}`).content.firstElementChild.cloneNode(true);
}

function announce(message) {
  ui.announcer.textContent = "";
  setTimeout(() => {
    ui.announcer.textContent = message;
  }, 50);
}

function createPoller(task, intervalMs) {
  let active = false;
  let running = false;
  let again = false;
  let timer = null;

  async function run() {
    clearTimeout(timer);
    timer = null;
    if (running) {
      again = true;
      return;
    }
    running = true;
    const started = Date.now();
    try {
      await task();
    } catch (error) {
      console.error(error);
    }
    running = false;
    if (!active) return;
    if (again) {
      again = false;
      run();
    } else {
      timer = setTimeout(run, Math.max(0, intervalMs - (Date.now() - started)));
    }
  }

  return {
    start() {
      if (active) return;
      active = true;
      run();
    },
    stop() {
      active = false;
      again = false;
      clearTimeout(timer);
      timer = null;
    },
    refresh() {
      if (active) run();
    },
  };
}

async function loadHardware() {
  const stamp = ++requestStamp;
  try {
    const hardware = await api.getHardware();
    if (!hardware || typeof hardware.mode !== "string") {
      throw new ApiError("The FloraBOT server sent an unexpected reply.", 502);
    }
    state.hardwareError = null;
    applyHardware(hardware, stamp);
  } catch (error) {
    state.hardwareError = error;
    render();
  }
}

async function loadCommands() {
  try {
    const commands = await api.getHardwareCommands(COMMAND_LIMIT);
    if (!Array.isArray(commands)) throw new ApiError("The FloraBOT server sent an unexpected reply.", 502);
    state.commandsError = null;
    renderLog(commands);
  } catch (error) {
    state.commandsError = error;
  }
  renderReachability();
}

function applyHardware(hardware, stamp) {
  if (stamp < state.hardwareStamp) return;
  state.hardwareStamp = stamp;
  const previous = state.hardware;
  state.hardware = hardware;

  const previousId = previous?.pending_command?.command_id ?? null;
  const command = hardware.pending_command ?? null;
  if ((command?.command_id ?? null) !== previousId) {
    if (command && previous) announce(`New command: ${command.led} ${command.requested_state} requested.`);
    commandsPoller.refresh();
  }
  render();
}

function render() {
  const hardware = state.hardware;
  renderMode(hardware);
  renderBoard(hardware);
  renderFacts(hardware);
  syncSimulation();
  renderCommand();
  renderReachability();
  renderClock();
}

function renderMode(hardware) {
  const badge = { dummy: ["Simulator", "badge-water"], real: ["Live monitor", "badge-leaf"] }[hardware?.mode];
  ui.modeBadge.hidden = !badge;
  if (badge) {
    setText(ui.modeBadge, badge[0]);
    ui.modeBadge.className = `badge ${badge[1]}`;
  }
  ui.realBanner.hidden = hardware?.mode !== "real";
  ui.simPanel.hidden = !(isDummy(hardware) && hardware.simulation);
}

function renderBoard(hardware) {
  const led = hardware?.led1_state;
  const known = led === "ON" || led === "OFF";
  const stale = Boolean(hardware && state.hardwareError);
  ui.board.dataset.led = known ? led.toLowerCase() : "unknown";
  ui.board.dataset.online = hardware ? String(Boolean(hardware.online)) : "unknown";
  ui.board.dataset.stale = String(stale);

  if (!hardware) {
    setText(ui.ledCaption, "Connecting to the FloraBOT server…");
    setText(ui.boardNote, "");
    return;
  }
  setText(ui.ledCaption, known ? `LED1 is ${led}` : "LED1 state unknown");
  const notes = [];
  if (isDummy(hardware)) notes.push("Simulated board.");
  if (!known) notes.push(`${capitalize(deviceName(hardware))} has not reported LED1 yet.`);
  else if (!hardware.online) notes.push("The board is offline, so this is the last reported state.");
  if (stale) notes.push("Showing the last update from the server.");
  setText(ui.boardNote, notes.join(" "));
}

function renderFacts(hardware) {
  setText(ui.factDevice, hardware?.device_id ?? "—");
  ui.factDot.dataset.online = hardware ? String(Boolean(hardware.online)) : "unknown";
  if (!hardware) {
    for (const node of [ui.factConnection, ui.factLed, ui.factMode]) setText(node, "—");
    for (const node of [ui.factLedSub, ui.factModeSub]) setText(node, "");
    return;
  }
  const led = hardware.led1_state;
  const known = led === "ON" || led === "OFF";
  const stale = Boolean(state.hardwareError);
  ui.factDot.dataset.online = stale ? "unknown" : String(Boolean(hardware.online));
  setText(ui.factConnection, stale ? "Unknown" : hardware.online ? "Online" : "Offline");
  setText(ui.factLed, known ? led : "Unknown");
  setText(ui.factLedSub, known ? "Last reported state" : "Not reported yet");
  setText(ui.factMode, hardware.label || (isDummy(hardware) ? "Simulated ESP32" : "ESP32"));
  setText(ui.factModeSub, `${capitalize(hardware.mode)} mode`);
}

function renderClock() {
  const hardware = state.hardware;
  if (hardware && state.hardwareError) {
    setText(ui.factSeen, `server unreachable; last known ${hardware.online ? "online" : "offline"}`);
  } else if (hardware) {
    const seen = parseTime(hardware.last_seen_at);
    setText(ui.factSeen, seen === null ? "not seen yet" : `last seen ${timeAgo(seen)}`);
  } else {
    setText(ui.factSeen, "");
  }
  const command = hardware?.pending_command;
  if (command) renderCountdown(hardware, command);
}

function renderCountdown(hardware, command) {
  const now = Date.now();
  const created = parseTime(command.created_at);
  const expires = parseTime(command.expires_at) ?? now;
  const total = created !== null && expires > created ? expires - created : 30000;
  const left = Math.max(0, expires - now);
  const fraction = Math.min(1, left / total);
  const seconds = Math.ceil(left / 1000);

  ui.countdownBar.style.transform = `scaleX(${fraction.toFixed(4)})`;
  ui.commandPanel.classList.toggle("is-urgent", fraction <= 0.2);
  setText(ui.countdownText, seconds > 0 ? `Expires in ${seconds} s` : "Expiring now…");
  setAttr(ui.countdownTrack, "aria-valuemax", String(Math.round(total / 1000)));
  setAttr(ui.countdownTrack, "aria-valuenow", String(seconds));
  setAttr(ui.countdownTrack, "aria-valuetext", seconds > 0 ? `${seconds} seconds left` : "Expiring now");
  setText(ui.commandNote, commandNote(hardware, command, now));
}

function commandNote(hardware, command, now) {
  if (!isDummy(hardware)) {
    const note = "Waiting for the ESP32 to confirm.";
    return hardware.online ? note : `${note} It has not checked in recently, so this may not be confirmed.`;
  }

  const behaviour = hardware.simulation?.behaviour;
  const delayMs = (hardware.simulation?.response_delay_seconds ?? 0) * 1000;
  const start = parseTime(command.delivered_at) ?? now;
  const seconds = Math.ceil((start + delayMs - now) / 1000);
  switch (behaviour) {
    case "AUTO":
      return seconds > 0 ? `Auto-confirming in ${seconds} s` : "Auto-confirming now…";
    case "FAILING":
      return seconds > 0 ? `Will report a failure in ${seconds} s` : "Reporting a failure now…";
    case "OFFLINE":
      return "The board is offline — this command will expire unconfirmed.";
    case "MANUAL":
      return "Choose what the simulated ESP32 reports back.";
    default:
      return "";
  }
}

function confirmationBlocked(hardware) {
  return isDummy(hardware) ? hardware.simulation?.behaviour === "OFFLINE" : !hardware.online;
}

function renderCommand() {
  const hardware = state.hardware;
  const command = hardware?.pending_command ?? null;
  const focusWasInActions = ui.manualActions.contains(document.activeElement);

  ui.commandEmpty.hidden = Boolean(command);
  ui.commandPending.hidden = !command;
  ui.commandStatus.hidden = !command;

  if (command) {
    const info = statusInfo(command.status);
    setText(ui.commandStatus, info.label);
    ui.commandStatus.className = `badge badge-${info.tone}`;
    setText(ui.commandState, command.requested_state);
    const delivered = parseTime(command.delivered_at);
    const device = deviceName(hardware);
    setText(ui.stepRequested, clockTime(parseTime(command.created_at)));
    ui.stepCollect.dataset.state = delivered === null ? "current" : "done";
    setText(ui.stepCollectTitle, delivered === null ? `Waiting for ${device} to collect it` : `Collected by ${device}`);
    setText(ui.stepCollectDetail, delivered === null ? "" : clockTime(delivered));
    ui.stepConfirm.dataset.state = confirmationBlocked(hardware) ? "blocked" : delivered === null ? "upcoming" : "current";

    ui.manualActions.hidden = !(isDummy(hardware) && hardware.simulation?.behaviour === "MANUAL");
    const busy = state.ackSending !== null || state.ackedCommandId === command.command_id;
    setText(ui.ackConfirm, state.ackSending === "confirm" ? "Confirming…" : `Apply ${command.requested_state} & confirm`);
    setText(ui.ackFail, state.ackSending === "fail" ? "Reporting…" : "Report failure");
    setAttr(ui.ackConfirm, "aria-disabled", String(busy));
    setAttr(ui.ackFail, "aria-disabled", String(busy));
    renderCountdown(hardware, command);
  } else {
    ui.commandPanel.classList.remove("is-urgent");
  }

  if (focusWasInActions && (ui.manualActions.hidden || ui.commandPending.hidden)) ui.commandTitle.focus();
}

function renderReachability() {
  const error = state.hardwareError ?? state.commandsError;
  const unreachable = Boolean(error);
  ui.unreachableBanner.hidden = !unreachable;
  setText(ui.unreachableDetail, error && error.status !== 0 ? errorMessage(error) : "");
  if (unreachable !== state.wasUnreachable) {
    announce(unreachable ? "Server unreachable. Retrying." : "Connected to the FloraBOT server again.");
  }
  state.wasUnreachable = unreachable;
}

async function acknowledge(success) {
  const command = state.hardware?.pending_command;
  if (!command || state.ackSending !== null || state.ackedCommandId === command.command_id) return;
  state.ackSending = success ? "confirm" : "fail";
  renderCommand();
  try {
    const result = await api.acknowledgeSimulatedCommand(command.command_id, success);
    state.ackedCommandId = result.command_id;
    log.flashed.add(result.command_id);
    showResolution(result, true);
  } catch (error) {
    log.flashed.add(command.command_id);
    showFlash("failure", errorMessage(error));
  } finally {
    state.ackSending = null;
    renderCommand();
    hardwarePoller.refresh();
    commandsPoller.refresh();
  }
}

function resolutionMessage(command, byHand) {
  // A no-break space keeps "LED1 ON" on one line when the message wraps.
  const what = `${command.led}\u00a0${command.requested_state}`;
  const device = capitalize(deviceName(state.hardware));
  switch (command.status) {
    case "ACKNOWLEDGED":
      return ["success", `Confirmed. ${device} reported ${command.led}\u00a0${command.acknowledged_state}.`];
    case "FAILED":
      return ["failure", byHand ? `Failure reported. ${what} is marked as failed.` : `Failed. ${device} could not complete ${what}.`];
    case "EXPIRED":
      return ["failure", `Expired. ${what} was not confirmed in time.`];
    case "SUPERSEDED":
      return ["neutral", `Replaced. A newer command took over from ${what}.`];
    default:
      return null;
  }
}

function showResolution(command, byHand = false) {
  const message = resolutionMessage(command, byHand);
  if (message) showFlash(...message);
}

function showFlash(tone, text) {
  clearTimeout(flashTimer);
  const flash = document.createElement("p");
  flash.className = `flash flash--${tone}`;
  const label = document.createElement("span");
  label.textContent = text;
  flash.append(icon(tone), label);
  ui.flashRegion.replaceChildren(flash);
  flashTimer = setTimeout(() => ui.flashRegion.replaceChildren(), FLASH_MS);
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  const text = document.createElement("p");
  text.className = "toast__text";
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast__close";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "×";
  close.addEventListener("click", () => toast.remove());
  toast.append(icon("failure"), text, close);
  ui.toasts.append(toast);
  setTimeout(() => toast.remove(), TOAST_MS);
}

function renderLog(commands) {
  const now = Date.now();
  let resolved = null;
  let anchor = ui.logList.firstElementChild;

  for (const command of commands) {
    const id = command.command_id;
    let row = log.rows.get(id);
    const isNew = !row;
    if (isNew) {
      row = createLogRow(id);
      log.rows.set(id, row);
    }
    updateLogRow(row, command);
    if (row === anchor) anchor = anchor.nextElementSibling;
    else ui.logList.insertBefore(row, anchor);
    if (isNew && log.primed) highlight(row);

    const before = log.statuses.get(id);
    const justClosed = before ? OPEN_STATUSES.has(before) : isNew && now - (parseTime(command.created_at) ?? 0) < RECENT_MS;
    if (log.primed && !resolved && justClosed && !OPEN_STATUSES.has(command.status) && !log.flashed.has(id)) {
      resolved = command;
    }
    log.statuses.set(id, command.status);
  }

  while (anchor) {
    const next = anchor.nextElementSibling;
    log.rows.delete(anchor.dataset.id);
    log.statuses.delete(anchor.dataset.id);
    anchor.remove();
    anchor = next;
  }

  ui.logEmpty.hidden = commands.length > 0;
  ui.logList.hidden = commands.length === 0;
  log.primed = true;
  if (resolved) {
    log.flashed.add(resolved.command_id);
    showResolution(resolved);
  }
}

function createLogRow(id) {
  const row = document.createElement("li");
  row.className = "log__row";
  row.dataset.id = id;
  const time = document.createElement("time");
  time.className = "log__time";
  const what = document.createElement("span");
  what.className = "log__what";
  const status = document.createElement("span");
  status.className = "badge log__status";
  const reported = document.createElement("span");
  reported.className = "log__reported";
  const failure = document.createElement("p");
  failure.className = "log__failure";
  row.append(time, what, status, reported, failure);
  return row;
}

function updateLogRow(row, command) {
  const [time, what, status, reported, failure] = row.children;
  const created = parseTime(command.created_at);
  setText(time, clockTime(created));
  setAttr(time, "datetime", created === null ? "" : new Date(created).toISOString());
  setText(what, `${command.led} ${command.requested_state}`);
  const info = statusInfo(command.status);
  setText(status, info.label);
  status.className = `badge badge-${info.tone} log__status`;
  const open = OPEN_STATUSES.has(command.status);
  setText(reported, command.acknowledged_state ? `Reported ${command.acknowledged_state}` : open ? "Awaiting report" : "No report");
  reported.classList.toggle("is-empty", !command.acknowledged_state);
  setText(failure, command.failure ?? "");
  failure.hidden = !command.failure;
}

function highlight(row) {
  row.classList.add("is-new");
  setTimeout(() => row.classList.remove("is-new"), HIGHLIGHT_MS);
}

function simulationBusy() {
  return simulation.sending || simulation.queued !== null || simulation.debounceTimer !== null;
}

function syncSimulation() {
  const settings = state.hardware?.simulation;
  if (!settings || simulationBusy()) return;
  simulation.behaviour = settings.behaviour;
  simulation.delay = settings.response_delay_seconds;
  paintSimulation();
}

function paintSimulation() {
  for (const input of ui.behaviourInputs) input.checked = input.value === simulation.behaviour;
  const usesDelay = DELAYED_BEHAVIOURS.has(simulation.behaviour);
  ui.delay.disabled = !usesDelay;
  ui.delayField.classList.toggle("is-inactive", !usesDelay);
  if (simulation.debounceTimer === null) ui.delay.value = String(Math.min(SLIDER_MAX_SECONDS, simulation.delay));
  setText(ui.delayValue, `${formatNumber(simulation.delay)} s`);
  setAttr(ui.delay, "aria-valuetext", `${formatNumber(simulation.delay)} seconds`);
}

function queueSimulation() {
  simulation.queued = { behaviour: simulation.behaviour, delay: simulation.delay };
  if (!simulation.sending) flushSimulation();
}

// Requests go out one at a time so the server always ends on the user's latest choice.
async function flushSimulation() {
  simulation.sending = true;
  while (simulation.queued) {
    const { behaviour, delay } = simulation.queued;
    simulation.queued = null;
    try {
      const hardware = await api.setSimulation(behaviour, delay);
      applyHardware(hardware, ++requestStamp);
    } catch (error) {
      showToast(errorMessage(error));
    }
  }
  simulation.sending = false;
  syncSimulation();
  renderCommand();
}

for (const input of ui.behaviourInputs) {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    simulation.behaviour = input.value;
    clearTimeout(simulation.debounceTimer);
    simulation.debounceTimer = null;
    paintSimulation();
    queueSimulation();
  });
}

ui.delay.addEventListener("input", () => {
  simulation.delay = Number(ui.delay.value);
  clearTimeout(simulation.debounceTimer);
  simulation.debounceTimer = setTimeout(() => {
    simulation.debounceTimer = null;
    queueSimulation();
  }, SLIDER_DEBOUNCE_MS);
  paintSimulation();
});

ui.ackConfirm.addEventListener("click", () => acknowledge(true));
ui.ackFail.addEventListener("click", () => acknowledge(false));

function nextTheme(theme) {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
}

function renderTheme() {
  const theme = window.FloraTheme.get();
  setText(ui.themeName, THEME_NAMES[theme]);
  ui.themeToggle.setAttribute("aria-label", `Theme: ${THEME_NAMES[theme]}. Switch to ${THEME_NAMES[nextTheme(theme)]}.`);
  for (const svg of ui.themeIcons) svg.toggleAttribute("hidden", svg.dataset.themeIcon !== theme);
}

if (window.FloraTheme) {
  ui.themeToggle.addEventListener("click", () => {
    window.FloraTheme.set(nextTheme(window.FloraTheme.get()));
    renderTheme();
  });
  window.addEventListener("florabot-themechange", renderTheme);
  renderTheme();
} else {
  ui.themeToggle.hidden = true;
}

const hardwarePoller = createPoller(loadHardware, HARDWARE_INTERVAL_MS);
const commandsPoller = createPoller(loadCommands, COMMANDS_INTERVAL_MS);

function syncPolling() {
  if (document.hidden) {
    hardwarePoller.stop();
    commandsPoller.stop();
  } else {
    hardwarePoller.start();
    commandsPoller.start();
  }
}

document.addEventListener("visibilitychange", syncPolling);
render();
syncPolling();
setInterval(renderClock, TICK_MS);
