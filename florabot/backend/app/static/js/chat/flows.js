import { h } from "./dom.js";
import { icon } from "./icons.js";
import { botRow, revealTop, say, userSays } from "./log.js";
import { action, reply, setQuickReplies } from "./quick-replies.js";
import { askCareQuestion, showCareIntro } from "./care.js";
import { analyzeStagedPhoto, canTakePhoto, focusComposer, hasStagedPhoto, pickPhoto, takePhoto } from "./composer.js";
import * as copy from "./content.js";
import { nav } from "./nav.js";

const ANALYZE_INTENT = /\b(analy[sz]e|photo|picture|upload|scan)\b/;
const HOW_INTENT = /how (does )?(florabot|it) work/;
const MENU_INTENT = /^(menu|help|start|hi|hello|hey)\b/;
const MAX_QUESTION_LENGTH = 500;

const MENU_ACTIONS = {
  analyze: () => analyzeIntro(),
  care: () => showCareIntro(),
  how: () => howItWorks(),
};

let menuCount = 0;

function staggered(row, index) {
  row.style.setProperty("--enter-delay", `${index * 140}ms`);
  return row;
}

function menuCards() {
  menuCount += 1;
  return h(
    "div",
    { class: "menu", role: "group", "aria-label": "Main menu" },
    copy.MENU.map((item) => {
      const id = `menu-${menuCount}-${item.id}`;
      return h(
        "button",
        {
          type: "button",
          class: `menu__item menu__item--${item.id}`,
          "aria-labelledby": `${id}-title`,
          "aria-describedby": `${id}-description`,
          onclick() {
            userSays(item.title);
            MENU_ACTIONS[item.id]();
            focusComposer();
          },
        },
        item.id === "analyze" ? h("span", { class: "menu__art", "aria-hidden": "true" }, icon("leaf")) : null,
        h("span", { class: "menu__icon" }, icon(item.icon)),
        h("span", { class: "menu__title", id: `${id}-title` }, item.title),
        h("span", { class: "menu__description", id: `${id}-description` }, item.description),
      );
    }),
  );
}

export function welcome() {
  const greeting = staggered(botRow(h("div", { class: "bubble bubble--greeting" }, h("p", {}, copy.WELCOME[0]))), 0);
  staggered(botRow(h("div", { class: "bubble" }, h("p", {}, copy.WELCOME[1]))), 1);
  staggered(botRow(menuCards()), 2);
  setQuickReplies([]);
  // Start reading at the greeting, even when the welcome is taller than a small screen.
  requestAnimationFrame(() => revealTop(greeting));
}

function showMenu() {
  say(copy.GREETING);
  botRow(menuCards());
  setQuickReplies([]);
}

function photoButtons() {
  const buttons = [h("button", { type: "button", class: "btn btn-primary btn-compact", onclick: pickPhoto }, icon("image"), "Choose a photo")];
  if (canTakePhoto()) {
    buttons.push(h("button", { type: "button", class: "btn btn-secondary btn-compact", onclick: takePhoto }, icon("camera"), "Take a photo"));
  }
  return h("div", { class: "bubble__actions" }, buttons);
}

function analyzeIntro() {
  say(
    copy.PHOTO_INTRO,
    h(
      "ul",
      { class: "leaf-list" },
      copy.PHOTO_TIPS.map((tip) => h("li", {}, tip)),
    ),
    canTakePhoto() ? null : h("p", { class: "bubble__hint" }, "You can also drop a photo onto this page or paste one."),
    photoButtons(),
  );
  setQuickReplies([reply("Back to menu", showMenu)]);
}

function howItWorks() {
  const steps = h(
    "ol",
    { class: "how" },
    copy.HOW_STEPS.map((step, index) =>
      h(
        "li",
        { class: "how__step" },
        h("span", { class: "how__icon" }, icon(step.icon), h("span", { class: "how__number", "aria-hidden": "true" }, String(index + 1))),
        h("div", { class: "how__text" }, h("p", { class: "how__title" }, step.title), h("p", { class: "how__detail" }, step.detail)),
      ),
    ),
  );
  say(copy.HOW_INTRO, steps);
  setQuickReplies([reply("Analyze My Plant", analyzeIntro), reply("Plant Care Assistance", showCareIntro), reply("Back to menu", showMenu)]);
}

function startAgain() {
  userSays("Start again");
  welcome();
}

function finish() {
  say(
    copy.FINISH_MESSAGE,
    h(
      "div",
      { class: "bubble__actions" },
      h(
        "button",
        {
          type: "button",
          class: "btn btn-secondary btn-compact",
          onclick() {
            startAgain();
            focusComposer();
          },
        },
        icon("refresh"),
        "Start again",
      ),
    ),
  );
  setQuickReplies([]);
}

function nextStepReplies() {
  return [action("Analyze another photo", pickPhoto), reply("Plant Care Assistance", showCareIntro), reply("Finish", finish)];
}

/**
 * The soil question carries its own answer buttons, so the advice always matches the result it follows,
 * whatever later messages do to the quick replies.
 */
function soilQuestion(answers) {
  const choices = h("div", { class: "soil-choices", role: "group", "aria-label": "Your soil check" });
  const option = (label, text) =>
    h(
      "button",
      {
        type: "button",
        class: "chip",
        "aria-pressed": "false",
        onclick(event) {
          for (const button of choices.querySelectorAll("button")) button.disabled = true;
          event.currentTarget.setAttribute("aria-pressed", "true");
          userSays(label);
          say(text);
          focusComposer();
        },
      },
      label,
    );
  choices.append(
    option("It's dry", answers.dry),
    option("It's still moist", answers.moist),
    option("Skip", "No problem. What would you like to do next?"),
  );
  return choices;
}

/** Follow-up once the newest analysis and its LED request are final. The soil check never changes the LED. */
function afterAnalysis(analysis) {
  const answers = copy.SOIL_REPLIES[analysis.recommendation];
  if (!answers) {
    // The uncertain result card already offers "Retry this photo" and "Analyze another photo".
    setQuickReplies([reply("Plant Care Assistance", showCareIntro), reply("Finish", finish)]);
    return;
  }
  say(h("p", { class: "soil-question" }, icon("hand"), h("span", {}, copy.SOIL_QUESTION)), soilQuestion(answers));
  setQuickReplies(nextStepReplies());
}

/**
 * Routes typed text: photo analysis, how it works, the menu, or a plant-care question.
 * Returns false when the text should stay in the message box for editing.
 */
export function handleText(text) {
  const question = text.trim();
  const normalized = question.toLowerCase();
  // Count characters the way the server does (an emoji is one character, not two).
  const length = [...question].length;
  if (ANALYZE_INTENT.test(normalized)) {
    userSays(text);
    if (hasStagedPhoto()) analyzeStagedPhoto();
    else analyzeIntro();
  } else if (HOW_INTENT.test(normalized)) {
    userSays(text);
    howItWorks();
  } else if (MENU_INTENT.test(normalized)) {
    userSays(text);
    showMenu();
  } else if (length < 2) {
    say("Please type a full question so I can help.");
    return false;
  } else if (length > MAX_QUESTION_LENGTH) {
    say(`Please keep your question under ${MAX_QUESTION_LENGTH} characters (it's ${length} now). You can edit it in the message box.`);
    return false;
  } else {
    userSays(text);
    askCareQuestion(question);
  }
  return true;
}

Object.assign(nav, { menu: showMenu, analyzeIntro, pickPhoto, afterAnalysis });
