import { h } from "./dom.js";
import { icon } from "./icons.js";
import { LEVEL_NAMES, QUALITY_NAMES, RESULT_NAMES, formatSeconds } from "./format.js";
import { readAloudButtonContent, speechSupported, toggleSpeech } from "./speech.js";

const VERDICTS = {
  WATERING_RECOMMENDED: { tone: "water", icon: "drop" },
  WATERING_NOT_RECOMMENDED: { tone: "leaf", icon: "leafCheck" },
  UNCERTAIN: { tone: "sun", icon: "questionMark" },
};

const CONFIDENCE_BARS = { LOW: 1, MEDIUM: 2, HIGH: 3 };

/** LED icon state for the hardware line. It only glows when the device confirmed LED1 is ON. */
function hardwareLedState(hardware) {
  if (hardware.confirmed_state === "ON") return "on";
  if (hardware.confirmed_state === "OFF") return "off";
  if (hardware.command_status === "PENDING" || hardware.command_status === "DELIVERED") return "waiting";
  if (hardware.command_status === null) return "unknown";
  return "failed";
}

function confidenceMeter(level) {
  if (!level) return null;
  const filled = CONFIDENCE_BARS[level];
  return h(
    "div",
    { class: "confidence", "data-level": filled },
    h("span", { class: "confidence__bars", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    `Confidence: ${LEVEL_NAMES[level]}`,
  );
}

function detailTags(analysis) {
  const tags = [];
  if (analysis.plant_detected !== null) {
    tags.push(
      h(
        "li",
        { class: `tag ${analysis.plant_detected ? "tag--yes" : "tag--no"}` },
        icon(analysis.plant_detected ? "check" : "close"),
        analysis.plant_detected ? "Plant detected" : "No plant detected",
      ),
    );
  }
  if (analysis.image_quality !== null) {
    tags.push(h("li", { class: "tag" }, icon("image"), `Image quality: ${QUALITY_NAMES[analysis.image_quality]}`));
  }
  return tags.length ? h("ul", { class: "result__tags", "aria-label": "Photo checks" }, tags) : null;
}

function observationList(observations) {
  if (observations.length === 0) return null;
  return h(
    "section",
    { class: "result__seen" },
    h("h4", { class: "result__subhead" }, "What I can see"),
    h(
      "ul",
      { class: "leaf-list" },
      observations.map((text) => h("li", {}, text)),
    ),
  );
}

function callout(kind, iconName, title, text) {
  return h(
    "div",
    { class: `callout callout--${kind}` },
    icon(iconName, "icon callout__icon"),
    h("div", {}, title ? h("p", { class: "callout__title" }, title) : null, h("p", {}, text)),
  );
}

/**
 * Renders a completed analysis. Server messages are shown verbatim.
 * Returns the element and updateHardware(hardware) for live LED updates.
 */
export function renderResult(analysis, { photoUrl, durationMs, onRetry, onAnotherPhoto }) {
  const verdict = VERDICTS[analysis.recommendation];
  const hardwareLed = h("span", { class: "led", "data-state": "waiting", "aria-hidden": "true" });
  const hardwareText = h("p", { class: "hwline__text" });
  let hardwareMessage = "";
  const diseaseSlot = h("div", { class: "result__disease" });
  let diseaseMessage = "";

  const thumb = h("img", { class: "result__thumb", src: photoUrl, alt: "The analyzed photo" });

  const actions = [];
  if (speechSupported) {
    const readButton = h("button", { type: "button", class: "btn btn-secondary btn-compact" }, readAloudButtonContent());
    readButton.addEventListener("click", () =>
      toggleSpeech(readButton, () =>
        [
          diseaseMessage ? `Plant health: ${diseaseMessage}` : "",
          analysis.message,
          analysis.observations.length ? `What I can see: ${analysis.observations.join(". ")}.` : "",
          hardwareMessage,
        ]
          .filter(Boolean)
          .join(" "),
      ),
    );
    actions.push(readButton);
  }
  if (analysis.recommendation === "UNCERTAIN") {
    const retryButton = h("button", { type: "button", class: "btn btn-secondary btn-compact" }, icon("refresh"), "Retry this photo");
    retryButton.addEventListener("click", () => {
      retryButton.disabled = true;
      onRetry();
    });
    actions.push(retryButton);
  }
  actions.push(h("button", { type: "button", class: "btn btn-primary btn-compact", onclick: onAnotherPhoto }, icon("camera"), "Analyze another photo"));

  const element = h(
    "section",
    { class: "result", "data-tone": verdict.tone, "aria-label": "Result" },
    h(
      "div",
      { class: "result__head" },
      h("h3", { class: "verdict" }, h("span", { class: "verdict__icon" }, icon(verdict.icon)), RESULT_NAMES[analysis.recommendation]),
      // A confidence level beside "Uncertain" reads as a contradiction, so it is only shown for watering results.
      analysis.recommendation === "UNCERTAIN" ? null : confidenceMeter(analysis.confidence_level),
      thumb,
    ),
    detailTags(analysis),
    diseaseSlot,
    h("p", { class: "result__message" }, analysis.message ?? ""),
    observationList(analysis.observations),
    analysis.uncertain_reason ? callout("sun", "question", "Why it's uncertain", analysis.uncertain_reason) : null,
    analysis.explanation ? h("p", { class: "result__explanation" }, analysis.explanation) : null,
    analysis.suggested_action ? callout("leaf", "hand", "Suggested action", analysis.suggested_action) : null,
    h("div", { class: "hwline" }, hardwareLed, hardwareText),
    h(
      "div",
      { class: "result__foot" },
      h("p", { class: "result__by" }, `Analyzed in ${formatSeconds(durationMs)}`),
    ),
    h("div", { class: "result__actions" }, actions),
  );

  return {
    element,
    updateHardware(hardware) {
      hardwareLed.dataset.state = hardwareLedState(hardware);
      if (hardware.message !== hardwareMessage) {
        hardwareMessage = hardware.message;
        hardwareText.textContent = hardware.message;
      }
    },
    /** Shows the plant-health check inside this card (or clears it for null); `speech` is used by Read aloud. */
    showHealth(panel, speech) {
      diseaseSlot.replaceChildren(...(panel ? [panel] : []));
      diseaseMessage = speech;
    },
    /** The chat stopped checking, so the LED icon no longer shows a request in progress. */
    stopWaiting() {
      if (hardwareLed.dataset.state === "waiting") hardwareLed.dataset.state = "unknown";
    },
  };
}
