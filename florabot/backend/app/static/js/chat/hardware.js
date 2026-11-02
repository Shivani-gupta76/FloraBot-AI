import { api } from "/js/api.js";
import { h } from "./dom.js";
import { icon } from "./icons.js";
import { timeAgo } from "./format.js";

const POLL_MS = 3000;

const root = document.getElementById("hw");
const button = document.getElementById("hw-button");
const led = document.getElementById("hw-led");
const ledText = document.getElementById("hw-led-text");
const statusText = document.getElementById("hw-status");
const simulatedTag = document.getElementById("hw-sim");
const pendingTag = document.getElementById("hw-pending");
const panel = document.getElementById("hw-panel");

const UNAVAILABLE_NOTE =
  "Device status isn't available right now. You can keep using the chat.";

const BEHAVIOUR_TEXT = {
  AUTO: (delay) => `Confirms automatically after ${delay} s`,
  MANUAL: () => "Waits for you to confirm on the ESP32 screen",
  FAILING: (delay) => `Reports a failure after ${delay} s`,
  OFFLINE: () => "Offline — not checking in",
};

let latest = null;
let simulated = null;
let timer = 0;
let busy = false;
let refreshAgain = false;
let panelTicker = 0;
let view = null;

// Safari before 17 and Firefox before 125 have no Popover API; there the panel is shown and hidden by hand.
const popoverSupported = typeof HTMLElement.prototype.togglePopover === "function";

/** True for the simulated ESP32, false for a real one, null until the first status arrives. */
export function isSimulated() {
  return simulated;
}

/** The simulator's behaviour (AUTO, MANUAL, FAILING, OFFLINE), or null for a real ESP32 or before the first status. */
export function simulationBehaviour() {
  return latest?.simulation?.behaviour ?? null;
}

function panelIsOpen() {
  return popoverSupported ? panel.matches(":popover-open") : !panel.hidden;
}

function panelOpened(open) {
  button.setAttribute("aria-expanded", String(open));
  clearInterval(panelTicker);
  if (open) panelTicker = setInterval(updateConnection, 1000);
}

function setUpPanelFallback() {
  panel.removeAttribute("popover");
  button.removeAttribute("popovertarget");
  panel.hidden = true;
  const close = () => {
    if (panel.hidden) return;
    panel.hidden = true;
    panelOpened(false);
  };
  button.addEventListener("click", () => {
    if (!panel.hidden) {
      close();
      return;
    }
    placePanel();
    panel.hidden = false;
    panelOpened(true);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      close();
      button.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!panel.contains(event.target) && !button.contains(event.target)) close();
  });
}

export function startHardwareStatus() {
  view = buildPanel();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(timer);
    else refreshHardware();
  });
  if (popoverSupported) {
    panel.addEventListener("beforetoggle", (event) => {
      if (event.newState === "open") placePanel();
    });
    panel.addEventListener("toggle", (event) => panelOpened(event.newState === "open"));
  } else {
    setUpPanelFallback();
  }
  window.addEventListener("resize", () => {
    if (panelIsOpen()) placePanel();
  });
  refreshHardware();
}

/** Fetches the hardware status now and restarts the 3-second polling cycle. */
export async function refreshHardware() {
  clearTimeout(timer);
  if (busy) {
    refreshAgain = true;
    return;
  }
  busy = true;
  try {
    latest = await api.getHardware();
    simulated = latest.mode === "dummy";
    render(latest);
  } catch {
    latest = null;
    renderUnavailable();
  } finally {
    busy = false;
  }
  if (refreshAgain) {
    refreshAgain = false;
    refreshHardware();
  } else if (!document.hidden) {
    timer = setTimeout(refreshHardware, POLL_MS);
  }
}

function ledState(value) {
  if (value === "ON") return "on";
  if (value === "OFF") return "off";
  return "unknown";
}

function render(status) {
  root.dataset.state = "ready";
  root.dataset.online = String(status.online);
  led.dataset.state = ledState(status.led1_state);
  ledText.textContent = status.led1_state ? `last reported ${status.led1_state}.` : "state unknown.";
  statusText.textContent = status.online ? "Online" : "Offline";
  simulatedTag.hidden = status.mode !== "dummy";
  pendingTag.hidden = status.pending_command === null;

  view.led.dataset.state = ledState(status.led1_state);
  view.title.textContent = status.label;
  view.list.hidden = false;
  view.note.hidden = true;
  updateConnection();
  view.ledValue.dataset.state = ledState(status.led1_state);
  view.ledName.textContent = { ON: "On", OFF: "Off" }[status.led1_state] ?? "Unknown";
  view.simulatorRow.hidden = status.simulation === null;
  if (status.simulation) {
    const { behaviour, response_delay_seconds: delay } = status.simulation;
    view.simulator.textContent = BEHAVIOUR_TEXT[behaviour]?.(delay) ?? behaviour;
  }
  view.pendingRow.hidden = status.pending_command === null;
  if (status.pending_command) view.pending.textContent = pendingText(status.pending_command, status.mode === "dummy");
}

function renderUnavailable() {
  root.dataset.state = "unavailable";
  delete root.dataset.online;
  led.dataset.state = "unknown";
  ledText.textContent = "state unknown.";
  statusText.textContent = "Status unavailable";
  simulatedTag.hidden = true;
  pendingTag.hidden = true;

  view.led.dataset.state = "unknown";
  view.title.textContent = "Device status unavailable";
  view.list.hidden = true;
  view.note.textContent = UNAVAILABLE_NOTE;
  view.note.hidden = false;
}

function updateConnection() {
  if (!latest) return;
  const seen = latest.last_seen_at ? `last seen ${timeAgo(latest.last_seen_at)}` : "not seen yet";
  view.connection.textContent = `${latest.online ? "Online" : "Offline"}, ${seen}`;
}

function pendingText(command, isDummy) {
  const device = isDummy ? "the simulated ESP32" : "the ESP32";
  const progress = command.status === "DELIVERED" ? `received by ${device}` : `waiting for ${device}`;
  return `${command.requested_state === "ON" ? "Turn on" : "Turn off"}, ${progress}`;
}

function row(term, ...value) {
  const description = h("dd", {}, ...value);
  return { element: h("div", { class: "hw-panel__row" }, h("dt", {}, term), description), description };
}

function buildPanel() {
  const panelLed = h("span", { class: "led", "data-state": "unknown", "aria-hidden": "true" });
  const title = h("h2", { class: "hw-panel__title", id: "hw-panel-title" }, "Hardware status");
  const ledValue = h("span", { class: "led", "data-state": "unknown", "aria-hidden": "true" });
  const ledName = h("span", {}, "Unknown");
  const connection = row("Connection");
  const ledRow = row("Watering LED", h("span", { class: "hw-panel__led" }, ledValue, ledName));
  const simulator = row("Simulation");
  const pending = row("Pending request");
  pending.description.classList.add("hw-panel__pending");
  const list = h(
    "dl",
    { class: "hw-panel__list", hidden: true },
    connection.element,
    ledRow.element,
    simulator.element,
    pending.element,
  );
  const note = h("p", { class: "hw-panel__note" }, "Checking the hardware status…");
  const link = h(
    "a",
    { class: "btn btn-secondary hw-panel__link", href: "/esp32.html", target: "_blank", rel: "noopener" },
    "Open ESP32 screen",
    icon("external"),
  );
  panel.replaceChildren(h("div", { class: "hw-panel__head" }, panelLed, title), list, note, link);
  return {
    led: panelLed,
    title,
    list,
    note,
    connection: connection.description,
    ledValue,
    ledName,
    simulatorRow: simulator.element,
    simulator: simulator.description,
    pendingRow: pending.element,
    pending: pending.description,
  };
}

function placePanel() {
  const rect = button.getBoundingClientRect();
  panel.style.setProperty("--panel-top", `${Math.round(rect.bottom + 8)}px`);
  panel.style.setProperty("--panel-right", `${Math.max(8, Math.round(window.innerWidth - rect.right))}px`);
}
