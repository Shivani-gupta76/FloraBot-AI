import { api, CONNECT_QR_URL } from "/js/api.js";
import { h } from "./dom.js";
import { icon } from "./icons.js";

const dialog = document.getElementById("phone-dialog");
const openButton = document.getElementById("phone-button");
const closeButton = document.getElementById("phone-close");
const body = document.getElementById("phone-body");

export function initConnectDialog() {
  openButton.addEventListener("click", open);
  closeButton.addEventListener("click", () => dialog.close());
  // A click on the dimmed backdrop lands on the <dialog> itself; clicks on the content land on its children.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => openButton.focus());
}

async function open() {
  const retrying = dialog.open;
  body.replaceChildren(h("p", { class: "sheet__loading" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Looking for this computer's network address…"));
  if (retrying) closeButton.focus();
  else dialog.showModal();
  let info = { url: null, reachable: false };
  try {
    info = await api.getConnectInfo();
  } catch {
    // Shown as "no address found" below.
  }
  if (!dialog.open) return;
  if (!info.url) body.replaceChildren(...noAddressView());
  else if (!info.reachable) body.replaceChildren(...notListeningView(info.url));
  else body.replaceChildren(...addressView(info.url));
}

function addressView(url) {
  const address = h("span", { class: "connect__url" }, url);
  const feedback = h("p", { class: "connect__feedback", role: "status" });
  const qr = h("img", { class: "connect__qr", src: CONNECT_QR_URL, alt: "QR code to open FloraBOT on your phone", width: 200, height: 200 });
  qr.addEventListener(
    "error",
    () => qr.replaceWith(h("p", { class: "connect__qr-missing" }, "The QR code could not be loaded. Type the address below into your phone's browser instead.")),
    { once: true },
  );
  const copyButton = h("button", { type: "button", class: "btn btn-secondary connect__copy", onclick: () => copy(url, address, feedback) }, icon("copy"), "Copy");
  return [
    h("p", { class: "sheet__lead" }, "Scan the code with your phone's camera, or open this address in its browser."),
    h("div", { class: "connect__qr-frame" }, qr),
    h("div", { class: "connect__address" }, address, copyButton),
    feedback,
    h("p", { class: "connect__hint" }, "Your phone needs to be on the same Wi-Fi network."),
  ];
}

/** The server only listens on this computer, so a QR code would lead the phone nowhere. */
function notListeningView(url) {
  return [
    h("p", { class: "sheet__lead" }, "Phones can't connect to this computer yet."),
    h(
      "p",
      { class: "connect__hint" },
      "Restart the server with ",
      h("code", {}, "--host 0.0.0.0"),
      " so devices on your Wi-Fi can reach ",
      h("span", { class: "connect__url connect__url--inline" }, url),
      ", then try again.",
    ),
    h("button", { type: "button", class: "btn btn-secondary", onclick: open }, icon("refresh"), "Try again"),
  ];
}

function noAddressView() {
  return [
    h("p", { class: "sheet__lead" }, "This computer isn't connected to a network."),
    h("p", { class: "connect__hint" }, "Connect it to Wi-Fi, then try again."),
    h("button", { type: "button", class: "btn btn-secondary", onclick: open }, icon("refresh"), "Try again"),
  ];
}

async function copy(url, address, feedback) {
  try {
    if (!navigator.clipboard) throw new Error("Clipboard unavailable");
    await navigator.clipboard.writeText(url);
    feedback.textContent = "Address copied.";
  } catch {
    window.getSelection()?.selectAllChildren(address);
    feedback.textContent = "Couldn't copy automatically. The address is selected — press ⌘C or Ctrl+C.";
  }
}
