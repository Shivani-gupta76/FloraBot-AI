import { h } from "./dom.js";
import { userSays } from "./log.js";
import { focusComposer } from "./composer.js";

const container = document.getElementById("quick-replies");

/** A quick reply the user "says": its label is echoed into the conversation before `run`. */
export function reply(label, run) {
  return {
    label,
    run() {
      userSays(label);
      run();
    },
  };
}

/** A quick action that does something without echoing a message (for example opening the photo picker). */
export function action(label, run) {
  return { label, run };
}

export function setQuickReplies(items) {
  container.replaceChildren(
    ...items.map(({ label, run }) =>
      h(
        "button",
        {
          type: "button",
          class: "chip",
          onclick() {
            run();
            focusComposer();
          },
        },
        label,
      ),
    ),
  );
  container.hidden = items.length === 0;
}
