import { icon } from "./icons.js";

export const speechSupported = "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance === "function";

let current = null;

function showState(button, speaking) {
  button.replaceChildren(icon(speaking ? "stop" : "speaker"), speaking ? "Stop" : "Read aloud");
}

function stop() {
  if (!current) return;
  const { button } = current;
  current = null;
  showState(button, false);
  window.speechSynthesis.cancel();
}

/** Starts reading `getText()` aloud with this button, or stops if the button is already reading. */
export function toggleSpeech(button, getText) {
  const wasThisButton = current?.button === button;
  stop();
  if (wasThisButton) return;
  const utterance = new SpeechSynthesisUtterance(getText());
  utterance.lang = document.documentElement.lang || "en";
  const finish = () => {
    if (current?.utterance === utterance) {
      current = null;
      showState(button, false);
    }
  };
  utterance.addEventListener("end", finish);
  utterance.addEventListener("error", finish);
  current = { button, utterance };
  showState(button, true);
  window.speechSynthesis.speak(utterance);
}

export function readAloudButtonContent() {
  return [icon("speaker"), "Read aloud"];
}
