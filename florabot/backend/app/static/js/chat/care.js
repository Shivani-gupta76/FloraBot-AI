import { api, ApiError } from "/js/api.js";
import { h, sleep } from "./dom.js";
import { icon } from "./icons.js";
import { bubble, say, showTyping, userSays } from "./log.js";
import { reply, setQuickReplies } from "./quick-replies.js";
import { focusComposer } from "./composer.js";
import { CARE_INTRO, CARE_TOPICS, CARE_TYPE_HINT } from "./content.js";
import { nav } from "./nav.js";
import { chosenModels } from "./ai-models.js";

const BULLET = /^(?:- |• )/;
const MIN_TYPING_MS = 500;

/** Plain text to DOM: blank lines separate paragraphs, and lines starting with "- " or "• " become a list. */
export function renderPlainText(text) {
  const nodes = [];
  for (const block of text.replace(/\r\n?/g, "\n").split(/\n\s*\n/)) {
    let list = null;
    let paragraph = null;
    for (const line of block.split("\n").map((part) => part.trim())) {
      if (!line) continue;
      if (BULLET.test(line)) {
        paragraph = null;
        if (!list) {
          list = h("ul", { class: "leaf-list" });
          nodes.push(list);
        }
        list.append(h("li", {}, line.replace(BULLET, "")));
      } else {
        list = null;
        if (paragraph) paragraph.append(h("br"));
        else {
          paragraph = h("p");
          nodes.push(paragraph);
        }
        paragraph.append(line);
      }
    }
  }
  return nodes;
}

function moreReplies() {
  return [
    reply("More care topics", showCareIntro),
    reply("Analyze My Plant", () => nav.analyzeIntro()),
    reply("Back to menu", () => nav.menu()),
  ];
}

export function showCareIntro() {
  const topics = h(
    "div",
    { class: "topics", role: "group", "aria-label": "Plant-care topics" },
    CARE_TOPICS.map((topic) =>
      h(
        "button",
        {
          type: "button",
          class: "chip",
          onclick() {
            answerTopic(topic);
            focusComposer();
          },
        },
        topic.question,
      ),
    ),
  );
  say(CARE_INTRO, topics, h("p", { class: "bubble__hint" }, CARE_TYPE_HINT));
  setQuickReplies([reply("Analyze My Plant", () => nav.analyzeIntro()), reply("Back to menu", () => nav.menu())]);
}

function answerTopic(topic) {
  userSays(topic.question);
  say(...renderPlainText(topic.answer));
  setQuickReplies(moreReplies());
}

/** Sends a typed question to the AI assistant and shows the answer, or the error with a way to try again. */
export async function askCareQuestion(question) {
  const typing = showTyping();
  try {
    const [answer] = await Promise.all([api.askCareQuestion(question, chosenModels().model ?? null), sleep(MIN_TYPING_MS)]);
    typing.replace(
      bubble(
        ...renderPlainText(answer.answer),
        h(
          "div",
          { class: "answer-meta" },
          h("p", { class: "answer-meta__source" }, icon("leaf"), "AI-generated answer"),
        ),
      ),
    );
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Something went wrong while asking the plant-care assistant.";
    const retry = h("button", { type: "button", class: "chip" }, icon("refresh"), "Try again");
    retry.addEventListener(
      "click",
      () => {
        retry.disabled = true;
        askCareQuestion(question);
        focusComposer();
      },
      { once: true },
    );
    typing.replace(h("div", { class: "bubble bubble--error" }, h("p", { class: "bubble__error" }, icon("alert"), message), retry));
  }
  setQuickReplies(moreReplies());
}
