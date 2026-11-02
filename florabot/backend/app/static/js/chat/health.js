import { h } from "./dom.js";
import { icon } from "./icons.js";
import { LEVEL_NAMES } from "./format.js";

const CONFIDENCE_BARS = { LOW: 1, MEDIUM: 2, HIGH: 3 };

const FINDINGS = {
  HEALTHY: { tone: "leaf", icon: "leafCheck", label: "Looks healthy" },
  DISEASE: { tone: "danger", icon: "disease", label: "Possible disease" },
  PEST: { tone: "danger", icon: "disease", label: "Possible pests" },
  NUTRIENT_OR_ENVIRONMENT: { tone: "sun", icon: "info", label: "Possible growing problem" },
  UNCLEAR: { tone: "sun", icon: "questionMark", label: "Not sure" },
};

const FINISHED = new Set(["DONE", "REVIEW_UNAVAILABLE"]);

function lower(level) {
  return LEVEL_NAMES[level].toLowerCase();
}

function initialVerdict(initial) {
  if (!initial) return "not available";
  if (initial.confidence_level === "LOW") return "not sure";
  return `${initial.crop} · ${initial.condition}`;
}

function reviewVerdict(review) {
  const finding = FINDINGS[review.finding] ?? FINDINGS.UNCLEAR;
  // An unclear review names the visible sign (for example "White specks on leaves") instead of a cause.
  if (review.finding === "UNCLEAR") return review.problem || finding.label;
  const plant = review.plant && review.plant.toLowerCase() !== "unknown" ? `${review.plant} · ` : "";
  return `${plant}${review.problem || finding.label}`;
}

function confidence(level) {
  return h(
    "span",
    { class: "confidence", "data-level": CONFIDENCE_BARS[level] },
    h("span", { class: "confidence__bars", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    `Confidence: ${LEVEL_NAMES[level]}`,
  );
}

/** True once the health check will not change any more (or there is none). */
export function healthFinished(health) {
  return !health || FINISHED.has(health.status);
}

/** Timeline step state and text. */
export function healthStep(health) {
  if (!health) return ["skipped", "Not available for this photo"];
  const { status, initial, review } = health;
  if (status === "CHECKING") return ["active", "Checking the leaves…"];
  if (status === "REVIEWING") return ["active", `Initial assessment: ${initialVerdict(initial)}. Looking into this in more detail…`];
  if (status === "DONE") {
    const confidenceText = review.finding === "UNCLEAR" ? "" : ` (${lower(review.confidence_level)} confidence)`;
    return ["done", `${reviewVerdict(review)}${confidenceText}`];
  }
  return initial ? ["done", `Initial assessment: ${initialVerdict(initial)}`] : ["failed", "The health check isn't available right now"];
}

/** What Read aloud says about plant health. */
export function healthSpeech(health) {
  if (health?.review) {
    const causes = health.review.possible_causes?.length ? ` Possible causes: ${health.review.possible_causes.join(", ")}.` : "";
    return `${reviewVerdict(health.review)}.${causes} ${health.review.advice}`;
  }
  return health?.initial?.message ?? "";
}

function initialBlock(initial) {
  if (!initial) return null;
  const tone = !initial.confident ? "sun" : initial.healthy ? "leaf" : "danger";
  return h(
    "div",
    { class: "disease__initial", "data-tone": tone },
    h("p", { class: "disease__label" }, "Initial assessment"),
    h(
      "div",
      { class: "disease__head" },
      h("span", { class: "disease__verdict" }, icon(initial.healthy && initial.confident ? "leafCheck" : "disease"), initialVerdict(initial)),
      confidence(initial.confidence_level),
    ),
    h("p", {}, initial.message),
  );
}

/** The plant-health part of the result card, or null while the leaf model is still running. */
export function healthPanel(health) {
  if (!health || health.status === "CHECKING") return null;
  const { status, initial, review } = health;
  const title = h("h4", { class: "result__subhead" }, "Plant health");

  if (status === "DONE") {
    const finding = FINDINGS[review.finding] ?? FINDINGS.UNCLEAR;
    return h(
      "section",
      { class: "disease", "data-tone": finding.tone },
      title,
      h(
        "div",
        { class: "disease__head" },
        h("span", { class: "disease__verdict" }, icon(finding.icon), reviewVerdict(review)),
        // A confidence level next to "not sure" would contradict it.
        review.finding === "UNCLEAR" ? null : confidence(review.confidence_level),
      ),
      review.possible_causes?.length ? h("p", { class: "disease__causes" }, `Possible causes: ${review.possible_causes.join(", ")}`) : null,
      review.observations.length ? h("ul", { class: "leaf-list" }, review.observations.map((text) => h("li", {}, text))) : null,
      h("p", { class: "disease__advice" }, review.advice),
      initial ? h("p", { class: "disease__more" }, `Initial assessment: ${initialVerdict(initial)}`) : null,
    );
  }

  const pending =
    status === "REVIEWING"
      ? h("p", { class: "disease__pending" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Looking into this in more detail…")
      : h("p", { class: "disease__more" }, "The detailed check isn't available right now.");
  return h("section", { class: "disease" }, title, initialBlock(initial), pending);
}
