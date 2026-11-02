import { api } from "/js/api.js";
import { h } from "./dom.js";

const KEY = "florabot-ai-models";

const button = document.getElementById("models-button");
const dialog = document.getElementById("models-dialog");
const closeButton = document.getElementById("models-close");
const fields = {
  model: { select: document.getElementById("model-select"), hint: document.getElementById("model-hint") },
  review_model: { select: document.getElementById("review-model-select"), hint: document.getElementById("review-model-hint") },
};

let options = null;

function saved() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) ?? {};
  } catch {
    return {};
  }
}

function save(choice) {
  try {
    localStorage.setItem(KEY, JSON.stringify(choice));
  } catch {
    // Storage can be blocked; the choice then lasts until the page reloads.
  }
}

function known(id) {
  return Boolean(id) && options.choices.some((choice) => choice.id === id);
}

/** The user's picks as request fields, or {} when the AI provider offers no choice. */
export function chosenModels() {
  if (!options?.choices.length) return {};
  const picks = saved();
  return {
    model: known(picks.model) ? picks.model : null,
    review_model: known(picks.review_model) ? picks.review_model : null,
  };
}

function current(name) {
  const pick = saved()[name];
  if (known(pick)) return pick;
  return name === "model" ? options.default_model : options.default_review_model;
}

function showHint(name) {
  const choice = options.choices.find((item) => item.id === fields[name].select.value);
  fields[name].hint.textContent = choice?.description ?? "";
}

function fill() {
  for (const [name, { select }] of Object.entries(fields)) {
    select.replaceChildren(...options.choices.map((choice) => h("option", { value: choice.id }, choice.label)));
    select.value = current(name);
    showHint(name);
  }
}

export async function initModelPicker() {
  try {
    options = await api.getModelOptions();
  } catch {
    options = null;
  }
  // The mock AI has nothing to choose, so the button stays hidden.
  if (!options?.choices.length) return;

  button.hidden = false;
  button.addEventListener("click", () => {
    fill();
    dialog.showModal();
  });
  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => button.focus());
  for (const [name, { select }] of Object.entries(fields)) {
    select.addEventListener("change", () => {
      save({ ...saved(), [name]: select.value });
      showHint(name);
    });
  }
}
