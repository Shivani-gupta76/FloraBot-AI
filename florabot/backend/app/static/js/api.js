// Client for the FloraBOT backend. Every call either returns the parsed JSON body
// or throws an ApiError whose message is safe to show to the user.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, { method = "GET", json, body, timeoutMs = 15000 } = {}) {
  const options = { method, headers: { Accept: "application/json" }, signal: AbortSignal.timeout(timeoutMs) };
  if (json !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(json);
  } else if (body !== undefined) {
    options.body = body;
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    const message =
      error.name === "TimeoutError"
        ? "The FloraBOT server took too long to respond. Please try again."
        : "I could not reach the FloraBOT server. Please check that it is running.";
    throw new ApiError(message, 0);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `The request failed (HTTP ${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return data;
}

export const api = {
  /** POST /api/analyses → { analysis_id, status }. `models` may hold { model, review_model } chosen by the user. */
  createAnalysis(file, models = {}) {
    const form = new FormData();
    form.append("image", file, file.name);
    for (const [name, value] of Object.entries(models)) {
      if (value) form.append(name, value);
    }
    return request("/api/analyses", { method: "POST", body: form, timeoutMs: 60000 });
  },

  /** GET /api/analyses/{id} → AnalysisOut */
  getAnalysis(analysisId) {
    return request(`/api/analyses/${encodeURIComponent(analysisId)}`, { timeoutMs: 10000 });
  },

  /** POST /api/care/answers → { answer, provider }. A slower model needs the longer timeout. */
  askCareQuestion(question, model = null) {
    return request("/api/care/answers", { method: "POST", json: { question, model }, timeoutMs: 180000 });
  },

  /** GET /api/ai/models → { choices: [{ id, label, description }], default_model, default_review_model } */
  getModelOptions() {
    return request("/api/ai/models", { timeoutMs: 8000 });
  },

  /** GET /api/hardware → HardwareStatusOut */
  getHardware() {
    return request("/api/hardware", { timeoutMs: 8000 });
  },

  /** GET /api/hardware/commands → DeviceCommandView[] (newest first) */
  getHardwareCommands(limit = 20) {
    return request(`/api/hardware/commands?limit=${encodeURIComponent(limit)}`, { timeoutMs: 8000 });
  },

  /** PUT /api/hardware/simulation → HardwareStatusOut (dummy mode only) */
  setSimulation(behaviour, responseDelaySeconds) {
    return request("/api/hardware/simulation", {
      method: "PUT",
      json: { behaviour, response_delay_seconds: responseDelaySeconds },
    });
  },

  /** POST /api/hardware/simulation/commands/{id}/ack → DeviceCommandView (dummy mode, MANUAL behaviour) */
  acknowledgeSimulatedCommand(commandId, success) {
    return request(`/api/hardware/simulation/commands/${encodeURIComponent(commandId)}/ack`, {
      method: "POST",
      json: { success },
    });
  },

  /** GET /api/connect → { url } where url may be null */
  getConnectInfo() {
    return request("/api/connect", { timeoutMs: 8000 });
  },
};

/** QR code (SVG) for the URL returned by getConnectInfo(). */
export const CONNECT_QR_URL = "/api/connect/qr.svg";
