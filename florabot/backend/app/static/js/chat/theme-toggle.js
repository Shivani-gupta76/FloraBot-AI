const ORDER = ["auto", "light", "dark"];
const NAMES = { auto: "Auto", light: "Light", dark: "Dark" };
const BAR_COLORS = { light: "#f4f1e8", dark: "#0e1712" };

const button = document.getElementById("theme-button");
const barColors = [...document.querySelectorAll('meta[name="theme-color"]')];
const systemBarColors = barColors.map((meta) => meta.content);

function nextTheme(theme) {
  return ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
}

function render() {
  const theme = window.FloraTheme.get();
  button.dataset.theme = theme;
  button.setAttribute("aria-label", `Theme: ${NAMES[theme]}`);
  button.title = `Theme: ${NAMES[theme]}. Switch to ${NAMES[nextTheme(theme)]}.`;
  barColors.forEach((meta, index) => {
    meta.content = BAR_COLORS[theme] ?? systemBarColors[index];
  });
}

export function initThemeToggle() {
  button.addEventListener("click", () => {
    window.FloraTheme.set(nextTheme(window.FloraTheme.get()));
    render();
  });
  window.addEventListener("florabot-themechange", render);
  render();
}
