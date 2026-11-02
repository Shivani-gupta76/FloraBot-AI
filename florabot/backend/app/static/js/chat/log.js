import { h } from "./dom.js";
import { icon } from "./icons.js";

const log = document.getElementById("log");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

// Shown when FloraBOT adds a message below the part of the conversation the reader is looking at.
const jumpButton = h(
  "button",
  { type: "button", class: "jump", hidden: true, onclick: () => scrollToEnd() },
  icon("arrowDown"),
  "New message",
);
log.after(jumpButton);

// True while the reader is at the end of the conversation (or being taken there), so new content stays in view.
let following = true;
let autoScrollUntil = 0;

function setFollowing(value) {
  following = value;
  if (value) jumpButton.hidden = true;
}

function isNearBottom() {
  return log.scrollHeight - log.scrollTop - log.clientHeight < 96;
}

function scrollLogTo(top, smooth) {
  const animate = smooth && !reduceMotion.matches;
  // Scroll events caused by our own scrolling must not be read as the reader scrolling away.
  autoScrollUntil = performance.now() + (animate ? 900 : 100);
  log.scrollTo({ top, behavior: animate ? "smooth" : "auto" });
}

log.addEventListener(
  "scroll",
  () => {
    if (performance.now() > autoScrollUntil) setFollowing(isNearBottom());
  },
  { passive: true },
);
log.addEventListener("scrollend", () => {
  autoScrollUntil = 0;
  setFollowing(isNearBottom());
});

// When the dock grows or shrinks (quick replies, photo tray), keep a following reader at the end.
new ResizeObserver(() => {
  if (following) scrollToEnd(false);
}).observe(log);

export function scrollToEnd(smooth = true) {
  jumpButton.hidden = true;
  scrollLogTo(log.scrollHeight, smooth);
}

/** Scrolls so the top of `element` sits near the top of the conversation. */
export function revealTop(element, smooth = true) {
  const top = log.scrollTop + element.getBoundingClientRect().top - log.getBoundingClientRect().top - 16;
  setFollowing(top >= log.scrollHeight - log.clientHeight - 96);
  scrollLogTo(top, smooth);
}

/**
 * Applies a change inside an existing message. If the reader is following the conversation, keeps the
 * newest content visible, or shows the top of `showTopOf` when it belongs to the newest message.
 */
export function keepInView(change, { showTopOf } = {}) {
  change();
  if (!following) return;
  if (showTopOf && log.lastElementChild?.contains(showTopOf)) revealTop(showTopOf);
  else scrollToEnd(false);
}

/** Appends a message row. The reader's own messages always scroll into view; FloraBOT's only if they are following. */
function addRow(row, { fromUser = false } = {}) {
  log.append(row);
  if (!fromUser && !following) {
    jumpButton.hidden = false;
    return row;
  }
  setFollowing(true);
  // Scroll on the next frame so quick replies set in the same step have already resized the log.
  requestAnimationFrame(() => {
    // A message taller than most of the view is shown from its top so it can be read in order.
    if (row.offsetHeight > log.clientHeight * 0.75) revealTop(row);
    else scrollToEnd();
  });
  return row;
}

function senderLabel(sender) {
  const previous = log.lastElementChild;
  if (previous?.dataset.sender === sender) return null;
  return h("span", { class: "visually-hidden" }, sender === "bot" ? "FloraBOT said:" : "You said:");
}

/** Adds a FloraBOT message row holding any content (bubbles, cards, menus). */
export function botRow(...content) {
  const label = senderLabel("bot");
  return addRow(
    h(
      "div",
      { class: "msg msg--bot", "data-sender": "bot" },
      h("div", { class: "msg__avatar", "aria-hidden": "true" }, icon("mark", "msg__mark")),
      h("div", { class: "msg__body" }, label, ...content),
    ),
  );
}

/** A FloraBOT speech bubble; strings become paragraphs. Returns the bubble. */
export function bubble(...content) {
  return h("div", { class: "bubble" }, ...content.map((part) => (typeof part === "string" ? h("p", {}, part) : part)));
}

export function say(...content) {
  const node = bubble(...content);
  botRow(node);
  return node;
}

export function userSays(text) {
  const label = senderLabel("user");
  return addRow(
    h("div", { class: "msg msg--user", "data-sender": "user" }, h("div", { class: "msg__body" }, label, h("div", { class: "bubble" }, h("p", {}, text)))),
    { fromUser: true },
  );
}

export function userPhoto(url, name) {
  const label = senderLabel("user");
  const image = h("img", { src: url, alt: "Your plant photo", decoding: "async" });
  const figure = h("figure", { class: "photo-bubble" }, image);
  const row = addRow(h("div", { class: "msg msg--user", "data-sender": "user" }, h("div", { class: "msg__body" }, label, figure)), {
    fromUser: true,
  });
  // The image height is unknown until it loads; keep a following reader at the end.
  image.addEventListener(
    "load",
    () => {
      if (following) scrollToEnd(false);
    },
    { once: true },
  );
  image.addEventListener(
    "error",
    () => {
      figure.classList.add("photo-bubble--missing");
      image.replaceWith(icon("image"), h("figcaption", {}, h("span", { class: "visually-hidden" }, "Your photo: "), name));
    },
    { once: true },
  );
  return row;
}

/** Shows animated typing dots; call replace() with the real content when it arrives. */
export function showTyping() {
  const body = h(
    "div",
    { class: "bubble bubble--typing" },
    h("span", { class: "typing", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    h("span", { class: "visually-hidden" }, "FloraBOT is typing…"),
  );
  botRow(body);
  return {
    replace(...content) {
      keepInView(() => body.replaceWith(...content));
    },
  };
}
