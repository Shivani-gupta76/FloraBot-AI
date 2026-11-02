const MB = 1024 * 1024;

export const RESULT_NAMES = {
  WATERING_RECOMMENDED: "Watering recommended",
  WATERING_NOT_RECOMMENDED: "Watering not recommended",
  UNCERTAIN: "Uncertain",
};

export const LEVEL_NAMES = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };

export const QUALITY_NAMES = { GOOD: "Good", ACCEPTABLE: "Acceptable", POOR: "Poor" };

export function formatBytes(bytes) {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Whole seconds until an ISO time, never negative. */
export function secondsUntil(iso) {
  return Math.max(0, Math.ceil((Date.parse(iso) - Date.now()) / 1000));
}

export function timeAgo(iso) {
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  if (seconds < 2) return "just now";
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}
