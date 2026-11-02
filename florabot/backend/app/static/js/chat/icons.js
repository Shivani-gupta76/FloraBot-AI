// Static SVG icons. Only the fixed strings below are parsed; no user or server text ever reaches the parser.
const SHAPES = {
  camera:
    '<path d="M4 8h3l1.6-2.5h6.8L17 8h3a1 1 0 0 1 1 1v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.2" r="3.4"/>',
  leaf: '<path d="M4.5 19.5C4.5 11 10 5 19.5 4.5 19 14 13 19.5 4.5 19.5z"/><path d="M4.5 19.5 12.5 11.5"/>',
  gear: '<path d="M9.32 5.53 10.43 5.18 10.66 2.49 13.34 2.49 13.57 5.18 14.68 5.53 15.71 6.06 17.78 4.33 19.67 6.22 17.94 8.29 18.47 9.32 18.82 10.43 21.51 10.66 21.51 13.34 18.82 13.57 18.47 14.68 17.94 15.71 19.67 17.78 17.78 19.67 15.71 17.94 14.68 18.47 13.57 18.82 13.34 21.51 10.66 21.51 10.43 18.82 9.32 18.47 8.29 17.94 6.22 19.67 4.33 17.78 6.06 15.71 5.53 14.68 5.18 13.57 2.49 13.34 2.49 10.66 5.18 10.43 5.53 9.32 6.06 8.29 4.33 6.22 6.22 4.33 8.29 6.06z"/><circle cx="12" cy="12" r="3"/>',
  mark: '<path class="mark-leaf" d="M4.5 19.5C4.5 11.3 9.6 6 18.9 5.6 18.6 14.7 13.4 19.5 4.5 19.5z" fill="currentColor" stroke="none"/><path class="mark-vein" d="M4.5 19.5 9 15h3.4M9 15v-3.3" stroke-width="1.6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="9.5" r="1.8"/><path d="m21 15.5-5-5L6 20"/>',
  upload: '<path d="M12 15V4.5M7.5 9 12 4.5 16.5 9"/><path d="M4.5 14.5v4a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-4"/>',
  drop: '<path d="M12 3.2c3.6 4.3 6.2 7.7 6.2 10.9a6.2 6.2 0 0 1-12.4 0c0-3.2 2.6-6.6 6.2-10.9z" fill="currentColor" stroke="none"/>',
  leafCheck:
    '<path d="M4.5 19.5C4.5 11 10 5 19.5 4.5 19 14 13 19.5 4.5 19.5z" fill="currentColor" stroke="none"/><path class="glyph-cut" d="m8.6 13.4 2.3 2.3 4.6-5" stroke-width="2"/>',
  question: '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.3a2.7 2.7 0 0 1 5.2 1c0 1.8-2.6 2.3-2.6 4"/><path d="M12 17.6h.01" stroke-width="2.4"/>',
  questionMark: '<path d="M9 9.2a3 3 0 0 1 5.9.9c0 2.1-2.9 2.5-2.9 4.6"/><path d="M12 18.4h.01" stroke-width="2.8"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  alert: '<path d="M10.3 4.3a2 2 0 0 1 3.4 0l7.6 13.2a2 2 0 0 1-1.7 3H4.4a2 2 0 0 1-1.7-3z"/><path d="M12 9.5v4.2"/><path d="M12 17h.01" stroke-width="2.4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.8h.01" stroke-width="2.4"/>',
  speaker: '<path d="M4 9.5h3.4L12 5.6v12.8l-4.6-3.9H4z"/><path d="M15.5 9.2a4 4 0 0 1 0 5.6M18.4 6.6a7.6 7.6 0 0 1 0 10.8"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2.2"/>',
  refresh: '<path d="M19.5 12.5A7.5 7.5 0 1 1 17.3 7"/><path d="M19.5 4.5v4.6h-4.6"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V6A2.5 2.5 0 0 0 13 3.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9.5 2.8V6M14.5 2.8V6M9.5 18v3.2M14.5 18v3.2M2.8 9.5H6M2.8 14.5H6M18 9.5h3.2M18 14.5h3.2"/><circle cx="12" cy="12" r="2.2"/>',
  shield: '<path d="M12 3 19.5 6v5.6c0 4.4-3.2 7.9-7.5 9.4-4.3-1.5-7.5-5-7.5-9.4V6z"/><path d="m8.8 12.1 2.2 2.2 4.2-4.3"/>',
  scan: '<path d="M4 8.5v-3A1.5 1.5 0 0 1 5.5 4h3M15.5 4h3A1.5 1.5 0 0 1 20 5.5v3M20 15.5v3a1.5 1.5 0 0 1-1.5 1.5h-3M8.5 20h-3A1.5 1.5 0 0 1 4 18.5v-3"/><path d="M8.5 15.5c0-4 2.6-6.9 7-7.1-.2 4.4-3 7.1-7 7.1z"/>',
  chatCheck:
    '<path d="M5 5h14a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5h-8.5L6 20v-3.5H5A1.5 1.5 0 0 1 3.5 15V6.5A1.5 1.5 0 0 1 5 5z"/><path d="m8.6 10.9 2.2 2.2 4.4-4.4"/>',
  hand: '<path d="M8 12.5V5.8a1.6 1.6 0 0 1 3.2 0v5.2M11.2 10.6V4.4a1.6 1.6 0 0 1 3.2 0v6.2M14.4 10.8V6.2a1.6 1.6 0 0 1 3.2 0v7.3c0 4-2.6 7-6.4 7-2.7 0-4.3-1.3-5.6-3.4l-2-3.4a1.5 1.5 0 0 1 2.5-1.6L8 13.9"/>',
  arrowDown: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5 11 13"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  disease: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/><path d="M8.5 11h5M11 8.5v5"/>',
};

const parser = new DOMParser();
const parsed = new Map();

export function icon(name, className = "icon") {
  let template = parsed.get(name);
  if (!template) {
    const source = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${SHAPES[name]}</svg>`;
    template = parser.parseFromString(source, "image/svg+xml").documentElement;
    parsed.set(name, template);
  }
  const svg = document.importNode(template, true);
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  return svg;
}
