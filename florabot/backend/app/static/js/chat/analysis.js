import { api } from "/js/api.js";
import { h, sleep } from "./dom.js";
import { icon } from "./icons.js";
import { botRow, keepInView, userPhoto } from "./log.js";
import { isSimulated, refreshHardware, simulationBehaviour } from "./hardware.js";
import { RESULT_NAMES, secondsUntil } from "./format.js";
import { renderResult } from "./result.js";
import { healthFinished, healthPanel, healthSpeech, healthStep } from "./health.js";
import { setQuickReplies } from "./quick-replies.js";
import { chosenModels } from "./ai-models.js";
import { focusComposer } from "./composer.js";
import { nav } from "./nav.js";

const POLL_MS = 1200;
// Long enough for the detailed health review on a slower model.
const GIVE_UP_MS = 5 * 60 * 1000;

const STEPS = [
  ["upload", "Photo received"],
  ["check", "Photo checked"],
  ["disease", "Health check"],
  ["look", "Water-stress check"],
  ["ready", "Recommendation"],
  ["led", "Watering LED"],
  ["confirm", "ESP32 confirmation"],
];

const STATE_NAMES = { pending: "not started", active: "in progress", done: "done", failed: "failed", skipped: "skipped" };

// Only the most recent analysis may ask follow-up questions, so answers always match the result on screen.
let latestRun = 0;

function deviceWording() {
  const simulated = isSimulated();
  if (simulated === null) {
    return {
      title: "Device confirmation",
      waiting: "Waiting for the device…",
      received: "The device received the request…",
    };
  }
  if (simulated) {
    return {
      title: "Simulated ESP32 confirmation",
      waiting: "Waiting for the simulated ESP32…",
      received: "The simulated ESP32 received the request…",
    };
  }
  return {
    title: "ESP32 confirmation",
    waiting: "Waiting for the ESP32…",
    received: "The ESP32 received the request…",
  };
}

/** A pointer to the ESP32 screen when the simulator is waiting on the user (Manual) or ignoring commands (Offline). */
function simulatorHint() {
  if (!isSimulated()) return null;
  const behaviour = simulationBehaviour();
  const link = (text) => h("a", { class: "stem__hint-link", href: "/esp32.html", target: "_blank", rel: "noopener" }, text, icon("external"));
  if (behaviour === "MANUAL") return { key: "manual", build: () => link("Confirm it on the ESP32 screen") };
  if (behaviour === "OFFLINE") return { key: "offline", build: () => link("The simulated ESP32 is set to Offline — change it on the ESP32 screen") };
  return null;
}

/** One row of the progress timeline. */
class Step {
  constructor(key, label) {
    this.label = h("span", { class: "stem__label" }, label);
    this.stateName = h("span", { class: "visually-hidden" });
    this.detail = h("span", { class: "stem__detail" });
    // The countdown changes every second, so it is hidden from screen readers to keep the live log quiet.
    this.countdown = h("span", { class: "stem__countdown", "aria-hidden": "true" });
    this.hint = h("span", { class: "stem__hint" });
    this.hintKey = null;
    this.element = h(
      "li",
      { class: "stem__step", "data-step": key },
      h("span", { class: "stem__node", "aria-hidden": "true" }),
      h("div", { class: "stem__text" }, this.label, this.stateName, this.detail, this.countdown, this.hint),
    );
    this.reset(label);
  }

  reset(label) {
    this.state = null;
    this.text = null;
    this.setLabel(label);
    this.set("pending");
  }

  setLabel(label) {
    if (this.label.textContent !== label) this.label.textContent = label;
  }

  set(state, text = "", { deadline = null, led = null, hint = null } = {}) {
    this.deadline = deadline;
    const hintKey = hint?.key ?? null;
    if (hintKey !== this.hintKey) {
      this.hintKey = hintKey;
      this.hint.replaceChildren(...(hint ? [hint.build()] : []));
    }
    if (led) this.element.dataset.led = led;
    else delete this.element.dataset.led;
    if (state !== this.state) {
      this.state = state;
      this.element.dataset.state = state;
      this.stateName.textContent = `: ${STATE_NAMES[state]}.`;
    }
    if (text !== this.text) {
      this.text = text;
      this.detail.textContent = text;
    }
    this.tick();
  }

  tick() {
    if (!this.deadline) {
      this.countdown.textContent = "";
      return;
    }
    const seconds = secondsUntil(this.deadline);
    this.countdown.textContent = seconds > 0 ? `${seconds} s left` : "expiring now";
  }
}

class AnalysisCard {
  constructor(file, photoUrl) {
    this.file = file;
    this.photoUrl = photoUrl;
    this.title = h("h2", { class: "analysis__title" }, "Analyzing your plant…");
    this.network = h("span", { class: "analysis__network", hidden: true }, h("span", { class: "spinner", "aria-hidden": "true" }), "reconnecting…");
    this.elapsed = h("span", { class: "analysis__elapsed", "aria-hidden": "true" }, "0 s");
    this.steps = Object.fromEntries(STEPS.map(([key, label]) => [key, new Step(key, label)]));
    this.notice = h("div", { class: "analysis__notice", hidden: true });
    this.resultSlot = h("div", { class: "analysis__result" });
    this.element = h(
      "article",
      { class: "analysis", "aria-label": "Plant photo analysis" },
      h("div", { class: "analysis__head" }, this.title, this.network, this.elapsed),
      h(
        "ol",
        { class: "stem", "aria-label": "Progress" },
        Object.values(this.steps).map((step) => step.element),
      ),
      this.notice,
      this.resultSlot,
    );
    this.ticker = 0;
    this.result = null;
  }

  async run() {
    this.runId = ++latestRun;
    this.reset();
    this.startedAt = performance.now();
    this.ticker = setInterval(() => this.tick(), 1000);
    keepInView(() => this.steps.upload.set("active", "Uploading…"));
    let created;
    try {
      created = await api.createAnalysis(this.file, chosenModels());
    } catch (error) {
      this.failUpload(error);
      return;
    }
    keepInView(() => {
      this.steps.upload.set("done");
      this.steps.check.set("done");
      this.steps.disease.set("active", "Checking the leaves…");
      this.steps.look.set("active");
    });
    await this.follow(created.analysis_id);
  }

  /** The plant-health check moves on by itself: local initial assessment first, then the AI's closer look. */
  showHealth(health) {
    const [state, text] = healthStep(health);
    this.steps.disease.set(state, text);
    const key = health ? `${health.status}:${Boolean(this.result)}` : "none";
    if (!this.result || key === this.healthKey) return;
    this.healthKey = key;
    this.result.showHealth(healthPanel(health), healthSpeech(health));
  }

  reset() {
    clearInterval(this.ticker);
    this.result = null;
    this.healthKey = null;
    this.followedUp = false;
    this.title.textContent = "Analyzing your plant…";
    this.network.hidden = true;
    this.elapsed.textContent = "0 s";
    for (const [key, label] of STEPS) this.steps[key].reset(label);
    this.steps.confirm.setLabel(deviceWording().title);
    this.notice.hidden = true;
    this.notice.replaceChildren();
    this.resultSlot.replaceChildren();
  }

  tick() {
    this.elapsed.textContent = `${Math.floor((performance.now() - this.startedAt) / 1000)} s`;
    this.steps.confirm.tick();
  }

  stopTicker() {
    clearInterval(this.ticker);
    this.tick();
  }

  async follow(analysisId) {
    const giveUpAt = Date.now() + GIVE_UP_MS;
    while (Date.now() < giveUpAt) {
      await sleep(POLL_MS);
      let analysis;
      try {
        analysis = await api.getAnalysis(analysisId);
      } catch (error) {
        if (error.status === 404) {
          this.stopWaiting("This result is no longer available. Please upload the photo again.", null);
          return;
        }
        this.network.hidden = false;
        continue;
      }
      this.network.hidden = true;
      this.show(analysis);
      const wateringDone = analysis.status === "COMPLETED" && analysis.hardware?.final;
      if (wateringDone && !this.followedUp) {
        this.followedUp = true;
        this.finishWatering(analysis);
      }
      if (wateringDone && healthFinished(analysis.health)) {
        this.stopTicker();
        return;
      }
    }
    this.stopWaiting("This is taking longer than usual. The server may be busy or offline.", analysisId);
  }

  /** Picks up an analysis that is already on the server after the chat stopped checking. */
  async resume(analysisId) {
    this.runId = ++latestRun;
    clearInterval(this.ticker);
    this.ticker = setInterval(() => this.tick(), 1000);
    keepInView(() => {
      this.title.textContent = this.result ? "Analysis complete" : "Analyzing your plant…";
      this.notice.hidden = true;
      this.notice.replaceChildren();
    });
    await this.follow(analysisId);
  }

  show(analysis) {
    if (analysis.status !== "COMPLETED") {
      keepInView(() => {
        this.steps.look.set("active", "Looking for drooping, curling or dry leaves…");
        this.showHealth(analysis.health);
      });
      return;
    }
    if (!this.result) {
      const durationMs = Date.parse(analysis.completed_at) - Date.parse(analysis.created_at);
      this.result = renderResult(analysis, {
        photoUrl: this.photoUrl,
        durationMs,
        onRetry: () => {
          analyzePhoto(this.file);
          focusComposer();
        },
        onAnotherPhoto: () => nav.pickPhoto(),
      });
      keepInView(
        () => {
          this.title.textContent = "Analysis complete";
          this.steps.look.set("done");
          this.steps.ready.set("done", RESULT_NAMES[analysis.recommendation]);
          this.showHardware(analysis.hardware);
          this.result.updateHardware(analysis.hardware);
          this.showHealth(analysis.health);
          this.resultSlot.replaceChildren(this.result.element);
        },
        { showTopOf: this.result.element },
      );
      return;
    }
    keepInView(() => {
      this.showHardware(analysis.hardware);
      this.result.updateHardware(analysis.hardware);
      this.showHealth(analysis.health);
    });
  }

  showHardware(hardware) {
    const { led, confirm } = this.steps;
    const words = deviceWording();
    confirm.setLabel(words.title);
    if (hardware.command_status === null) {
      led.set("skipped", "Unchanged for an uncertain result");
      confirm.set("skipped", "Nothing to confirm");
      return;
    }
    led.set("done", hardware.requested_state === "ON" ? "Turn-on requested" : "Turn-off requested");
    switch (hardware.command_status) {
      case "PENDING":
        confirm.set("active", words.waiting, { deadline: hardware.expires_at, hint: simulatorHint() });
        break;
      case "DELIVERED":
        confirm.set("active", words.received, { deadline: hardware.expires_at, hint: simulatorHint() });
        break;
      case "ACKNOWLEDGED":
        confirm.set("done", hardware.confirmed_state === "ON" ? "Watering LED is on" : "Watering LED is off", {
          led: hardware.confirmed_state === "ON" ? "on" : "off",
        });
        break;
      case "FAILED":
        confirm.set("failed", "The LED could not be switched");
        break;
      case "EXPIRED":
        confirm.set("failed", "No confirmation in time");
        break;
      case "SUPERSEDED":
        confirm.set("failed", "Replaced by a newer photo");
        break;
    }
  }

  /** The watering result and LED are final; the health check may still be finishing. */
  finishWatering(analysis) {
    refreshHardware();
    // A newer photo is already on its way, or this LED request was replaced: the follow-up belongs to the newer card.
    if (this.runId !== latestRun || analysis.hardware.command_status === "SUPERSEDED") return;
    nav.afterAnalysis(analysis);
  }

  failUpload(error) {
    this.stopTicker();
    keepInView(() => {
      if (error.status === 422) {
        // The photo reached the server but failed the image check; sending the same file again cannot help.
        this.title.textContent = "Photo not accepted";
        this.steps.upload.set("done");
        this.steps.check.set("failed", error.message);
        this.steps.disease.set("skipped", "Skipped because the photo wasn't accepted");
        this.showNotice(null, [noticeButton("Choose another photo", "image", () => nav.pickPhoto(), { once: false })]);
        return;
      }
      this.title.textContent = "Couldn't upload the photo";
      this.steps.upload.set("failed", error.message);
      this.steps.disease.set("skipped", "Skipped because the photo wasn't uploaded");
      this.showNotice(null, [
        noticeButton("Retry", "refresh", () => this.run()),
        noticeButton("Choose another photo", "image", () => nav.pickPhoto(), { once: false }),
      ]);
    });
  }

  stopWaiting(message, analysisId) {
    this.stopTicker();
    keepInView(() => {
      this.title.textContent = "Still waiting for a result";
      this.network.hidden = true;
      for (const step of Object.values(this.steps)) {
        if (step.state === "active") step.set("failed", "Stopped waiting");
      }
      this.result?.stopWaiting();
      const button = analysisId
        ? noticeButton("Keep checking", "refresh", () => this.resume(analysisId))
        : noticeButton("Upload again", "refresh", () => this.run());
      this.showNotice(message, [button]);
    });
  }

  showNotice(message, buttons) {
    const actions = h("div", { class: "analysis__notice-actions" }, buttons);
    if (message) this.notice.replaceChildren(h("p", { class: "analysis__notice-text" }, icon("alert"), message), actions);
    else this.notice.replaceChildren(actions);
    this.notice.hidden = false;
  }
}

function noticeButton(label, iconName, run, { once = true } = {}) {
  const button = h("button", { type: "button", class: "btn btn-secondary btn-compact" }, icon(iconName), label);
  button.addEventListener("click", () => {
    if (once) button.disabled = true;
    run();
    focusComposer();
  });
  return button;
}

/** Posts the user's photo and follows the analysis and the LED confirmation in one live card. */
export function analyzePhoto(file) {
  // Suggestions from an earlier result must not stay active under the new photo.
  setQuickReplies([]);
  const photoUrl = URL.createObjectURL(file);
  userPhoto(photoUrl, file.name);
  const card = new AnalysisCard(file, photoUrl);
  botRow(card.element);
  card.run();
}
