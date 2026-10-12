# Flora-Bot dashboard

Responsive React dashboard for the FastAPI service in `../backend`. Normal mode reads authenticated records from the API and shows accurate empty states. Demo Mode is an opt-in browser-only provider with fixed example crops, detections, watering events, alerts, rover telemetry and coordinates. Demo records and edits never call write endpoints or enter PostgreSQL; changes reset on page reload.

## Run locally

Use Node.js 20.19+ (Node 22 recommended):

```powershell
cd D:\Florabot\frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL` in `.env` to the FastAPI origin (default `http://localhost:8000`), then allow the Vite origin (usually `http://localhost:5173`) in the backend `ALLOWED_ORIGINS`. The optional `VITE_POLL_INTERVAL_MS` controls refresh cadence; requests are paused while the browser tab is hidden. The interface calls `/health` to report API process availability. This is not a PostgreSQL or hardware health check.

For a production bundle, run `npm run build`; preview it with `npm run preview`.

## Pages and API integration

- Overview: `/api/plants`, `/api/detections`, `/api/robot/status`, `/api/watering/history`, `/api/alerts`.
- Crop management: create, list, update and delete through `/api/plants` and `/api/plants/{id}`. Deletion is Admin-only in the backend.
- Disease detection: reads `/api/detections`; when a configured local model is available, an authenticated leaf-image workflow calls `/api/detections/infer` and stores the actual classifier result. Uploaded images are processed in memory and not stored. Without model weights/runtime, inference reports unavailable; demo predictions are labeled examples.
- Sensor readings remain supported by the backend API but are intentionally absent from the dashboard interface.
- Irrigation: `/api/watering/history`. This is a record-only workflow; the backend has no pump command endpoint, so no hardware control is offered.
- Rover: `/api/robot/status`. No movement control, WebSocket/SSE, camera status or independent heartbeat endpoint is exposed.
- GPS: coordinates from plants, detections and telemetry; demo coordinates are explicitly marked as examples, while real mode only displays submitted coordinates.
- Alerts: `/api/alerts` and `/api/alerts/{id}/read`.
- Reports & history: current API event lists and CSV export of retrieved event records.
- Settings: `/api/auth/me`, API URL and `/health` status, inference availability, and persistent Demo Mode selection.

All protected requests use the returned bearer token. The token is held in session storage and cleared when the user signs out or the backend returns 401. Login/registration payloads follow the backend JSON schemas. The browser never connects directly to PostgreSQL and no backend secrets are bundled.

## Current limitations

The backend has no date-range query for detections, no server-side crop pagination, no command route for irrigation or rover movement, and no streaming updates. Filtering available fields is local to records returned by the current API. The frontend polls at a conservative configurable interval while visible. Location display is a coordinate table with external map links. Hardware telemetry remains unavailable until actual devices submit it.
