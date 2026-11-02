// Load in <head> as a classic script so the saved theme applies before the page paints.
// "auto" (nothing saved) follows the system light/dark setting.
(() => {
  const KEY = "florabot-theme";
  const root = document.documentElement;

  function apply(theme) {
    if (theme === "light" || theme === "dark") root.dataset.theme = theme;
    else delete root.dataset.theme;
  }

  let saved = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch {
    // Storage can be blocked (private mode); the system theme still works.
  }
  apply(saved);

  // Another FloraBOT tab changed the theme: apply it here too and let this page's toggle update.
  window.addEventListener("storage", (event) => {
    if (event.key !== KEY && event.key !== null) return;
    apply(event.newValue);
    window.dispatchEvent(new Event("florabot-themechange"));
  });

  window.FloraTheme = {
    get: () => root.dataset.theme ?? "auto",
    set(theme) {
      apply(theme);
      try {
        if (theme === "light" || theme === "dark") localStorage.setItem(KEY, theme);
        else localStorage.removeItem(KEY);
      } catch {
        // Ignore storage errors; the theme still applies for this page view.
      }
    },
  };
})();
