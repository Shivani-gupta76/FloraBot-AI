const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = Math.max(1_000, Number(import.meta.env.VITE_API_TIMEOUT_MS) || 20_000);

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) { super(message); this.status = status; this.detail = detail; }
}

export async function request(path, { token, signal, ...options } = {}) {
  let response;
  let payload;
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener('abort', abortFromCaller, { once: true });
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    payload = response.status === 204 ? null : await response.json();
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timedOut) throw new ApiError(`Request timed out after ${Math.round(REQUEST_TIMEOUT_MS / 1000)} seconds. Retry when the API is responsive.`, 408);
    if (error.name === 'AbortError') throw error;
    if (response) throw new ApiError('The API returned an unreadable response.', response.status);
    throw new ApiError('Could not reach the Flora-Bot API. Check the server and API URL.');
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
  if (!response.ok) {
    const detail = payload?.detail;
    let message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((item) => item.msg).join(', ') : `Request failed (${response.status})`;
    if (response.status === 401) message = 'Your session is missing or has expired. Please sign in again.';
    if (response.status === 403) message = 'Your account does not have permission for this action.';
    if (response.status >= 500) message = 'The server could not complete this request. Please try again.';
    throw new ApiError(message, response.status, detail);
  }
  return payload;
}

export const api = {
  health: (signal) => request('/health', { signal }),
  login: (data) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  register: (data) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  me: (token, signal) => request('/api/auth/me', { token, signal }),
  summary: (token, signal) => request('/api/dashboard/summary', { token, signal }),
  plants: (token, signal) => request('/api/plants', { token, signal }),
  createPlant: (token, data) => request('/api/plants', { token, method: 'POST', body: JSON.stringify(data) }),
  updatePlant: (token, id, data) => request(`/api/plants/${id}`, { token, method: 'PUT', body: JSON.stringify(data) }),
  deletePlant: (token, id) => request(`/api/plants/${id}`, { token, method: 'DELETE' }),
  detections: (token, signal) => request('/api/detections?limit=500', { token, signal }),
  inferenceStatus: (token, signal) => request('/api/inference/status', { token, signal }),
  inferImage: (token, file, plantId) => request(`/api/detections/infer${plantId ? `?plant_id=${encodeURIComponent(plantId)}` : ''}`, { token, method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } }),
  sensorsLatest: (token, signal) => request('/api/sensors/latest', { token, signal }),
  sensorsHistory: (token, signal) => request('/api/sensors/history?limit=500', { token, signal }),
  telemetry: (token, signal) => request('/api/robot/status', { token, signal }),
  watering: (token, signal) => request('/api/watering/history?limit=500', { token, signal }),
  alerts: (token, signal) => request('/api/alerts?limit=500', { token, signal }),
  markAlertRead: (token, id) => request(`/api/alerts/${id}/read`, { token, method: 'PUT' }),
};

export function timestamp(value, options = {}) {
  if (!value) return 'No data available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown time';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', ...options }).format(date);
}

export function relativeTime(value) {
  if (!value) return 'No update received';
  const age = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(age)) return 'Unknown time';
  if (age < 60_000) return 'Updated just now';
  if (age < 3_600_000) return `Updated ${Math.floor(age / 60_000)}m ago`;
  if (age < 86_400_000) return `Updated ${Math.floor(age / 3_600_000)}h ago`;
  return timestamp(value);
}

export function saveCsv(filename, rows) {
  if (!rows.length) return false;
  const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  const csv = [headers.map(quote).join(','), ...rows.map((row) => headers.map((key) => quote(row[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
  return true;
}
