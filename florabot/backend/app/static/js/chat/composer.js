import { h } from "./dom.js";
import { icon } from "./icons.js";
import { say } from "./log.js";
import { formatBytes } from "./format.js";
import { PhotoError, nameForPastedImage, preparePhoto } from "./photo.js";

const form = document.getElementById("composer");
const input = document.getElementById("composer-input");
const sendButton = document.getElementById("send-button");
const attachButton = document.getElementById("attach-button");
const cameraButton = document.getElementById("camera-button");
const fileInput = document.getElementById("file-input");
const cameraInput = document.getElementById("camera-input");
const tray = document.getElementById("tray");
const trayStatus = document.getElementById("tray-status");
const dropzone = document.getElementById("dropzone");
const coarsePointer = matchMedia("(pointer: coarse)");

let handlers = { onText() {}, onAnalyze() {} };
let staged = null;
let stageToken = 0;

export function initComposer({ onText, onAnalyze }) {
  handlers = { onText, onAnalyze };
  form.addEventListener("submit", submit);
  // Keep the keyboard focus (and the phone keyboard) in the text field when Send is clicked or tapped.
  sendButton.addEventListener("pointerdown", (event) => event.preventDefault());
  attachButton.addEventListener("click", pickPhoto);
  cameraButton.addEventListener("click", takePhoto);
  for (const picker of [fileInput, cameraInput]) {
    picker.addEventListener("change", () => {
      const [file] = picker.files;
      picker.value = "";
      if (file) stagePhoto(file);
    });
  }
  showCameraButton();
  coarsePointer.addEventListener("change", showCameraButton);
  listenForDroppedFiles();
  document.addEventListener("paste", pastePhoto);
}

export function canTakePhoto() {
  return coarsePointer.matches;
}

export function pickPhoto() {
  fileInput.click();
}

export function takePhoto() {
  cameraInput.click();
}

/** Moves focus to the message field, except on touch screens where that would pop up the keyboard. */
export function focusComposer() {
  if (!coarsePointer.matches) input.focus({ preventScroll: true });
}

export function hasStagedPhoto() {
  return staged !== null;
}

export function analyzeStagedPhoto() {
  if (!staged) return;
  const { file } = staged;
  clearTray();
  handlers.onAnalyze(file);
  focusComposer();
}

function showCameraButton() {
  cameraButton.hidden = !coarsePointer.matches;
}

function submit(event) {
  event.preventDefault();
  const text = input.value.trim();
  if (text) {
    if (handlers.onText(text) !== false) input.value = "";
  } else if (staged) {
    analyzeStagedPhoto();
  }
  if (document.activeElement === sendButton || document.activeElement === document.body) input.focus({ preventScroll: true });
}

async function stagePhoto(file, { focusAnalyze = true } = {}) {
  const token = ++stageToken;
  renderPreparing(file);
  let prepared;
  try {
    prepared = await preparePhoto(file);
  } catch (error) {
    if (token !== stageToken) return;
    clearTray();
    say(error instanceof PhotoError ? error.message : "Something went wrong while preparing this photo. Please try another one.");
    return;
  }
  if (token !== stageToken) return;
  const analyzeButton = renderStaged(prepared);
  if (focusAnalyze) analyzeButton.focus({ preventScroll: true });
}

function clearTray() {
  stageToken++;
  if (staged) URL.revokeObjectURL(staged.url);
  staged = null;
  tray.replaceChildren();
  tray.hidden = true;
  trayStatus.textContent = "";
}

function removeStagedPhoto() {
  clearTray();
  input.focus({ preventScroll: true });
}

function thumbnail(url) {
  if (!url) return h("span", { class: "tray__thumb tray__thumb--empty", "aria-hidden": "true" }, icon("image"));
  const image = h("img", { class: "tray__thumb", src: url, alt: "" });
  image.addEventListener("error", () => image.replaceWith(thumbnail(null)), { once: true });
  return image;
}

function renderPreparing(file) {
  if (staged) URL.revokeObjectURL(staged.url);
  staged = null;
  tray.replaceChildren(
    thumbnail(null),
    h(
      "div",
      { class: "tray__info" },
      h("p", { class: "tray__name" }, file.name || "Pasted photo"),
      h("p", { class: "tray__meta" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Preparing photo…"),
    ),
  );
  tray.hidden = false;
  trayStatus.textContent = "Preparing photo…";
}

function renderStaged({ file, originalSize, note }) {
  const url = URL.createObjectURL(file);
  staged = { file, url };
  let status = null;
  let statusText = "";
  if (originalSize) {
    statusText = `Resized from ${formatBytes(originalSize)} to ${formatBytes(file.size)}`;
    status = h("p", { class: "tray__note" }, icon("check"), statusText);
  } else if (note) {
    statusText = note;
    status = h("p", { class: "tray__note tray__note--warn" }, icon("info"), note);
  }
  const analyzeButton = h("button", { type: "button", class: "btn btn-primary", onclick: analyzeStagedPhoto }, icon("scan"), "Analyze this photo");
  tray.replaceChildren(
    thumbnail(url),
    h(
      "div",
      { class: "tray__info" },
      h("p", { class: "tray__name" }, file.name),
      originalSize ? null : h("p", { class: "tray__meta" }, formatBytes(file.size)),
      status,
    ),
    h(
      "div",
      { class: "tray__actions" },
      analyzeButton,
      h("button", { type: "button", class: "btn btn-ghost", onclick: removeStagedPhoto }, "Remove"),
    ),
  );
  tray.hidden = false;
  trayStatus.textContent = `Photo ready: ${file.name}, ${formatBytes(file.size)}. ${statusText}`;
  return analyzeButton;
}

function listenForDroppedFiles() {
  let depth = 0;
  const carriesFiles = (event) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  const hideOverlay = () => {
    depth = 0;
    dropzone.hidden = true;
  };
  window.addEventListener("dragenter", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    depth += 1;
    dropzone.hidden = false;
  });
  window.addEventListener("dragover", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", (event) => {
    if (!carriesFiles(event)) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) dropzone.hidden = true;
  });
  window.addEventListener("drop", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    hideOverlay();
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;
    if (files.length > 1) say("I can check one photo at a time, so I picked the first one.");
    stagePhoto(files[0]);
  });
  window.addEventListener("dragend", hideOverlay);
}

function pastePhoto(event) {
  const [file] = Array.from(event.clipboardData?.files ?? []);
  if (!file) return;
  event.preventDefault();
  stagePhoto(nameForPastedImage(file), { focusAnalyze: false });
}
