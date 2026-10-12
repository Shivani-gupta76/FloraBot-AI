# Flora-Bot Crop Care Backend

FastAPI/PostgreSQL API for actual Flora-Bot records. It stores values received from clients and devices; it does not simulate readings, locations, detections, robot state, or watering. The database starts empty.

## Architecture and hardware flow

`ESP32 sensors and irrigation hardware → Raspberry Pi → this FastAPI service → PostgreSQL → React dashboard`

The ESP32/Raspberry Pi sends timestamped sensor readings, robot telemetry, completed watering events, and YOLO11n inference results to the API. The trained `flora_bot_best.pt` file stays on the inference host; this backend validates a result against the model's 15 known class labels and records the submitted prediction and confidence status. An uncertain/review result is stored as such and creates a review alert; it is never represented as a confirmed disease. Disease events do not start irrigation. Irrigation control and moisture thresholds belong to robot-side control logic; the API records what happened.

## Requirements and setup

- Python 3.11 or newer
- PostgreSQL 14 or newer

From this `backend` directory, create a virtual environment and install dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create an empty PostgreSQL database (for example, `florabot`) and set `DATABASE_URL` in `.env` to a SQLAlchemy psycopg URL, e.g. `postgresql+psycopg://<user>:<password>@<host>:5432/florabot`. Set `SECRET_KEY` to a long random secret before starting the service. Set `ALLOWED_ORIGINS` to the exact React origin(s), comma-separated. Never commit `.env` or real secrets.

Apply the schema and launch the service:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive API docs are at `/docs`; OpenAPI JSON is at `/openapi.json`. `/health` checks process availability only. Database connectivity is exercised when an API request queries the database.

Optional leaf-image inference is available when the trained YOLO11n-cls weights and Ultralytics runtime are installed on the backend host. Install `requirements-inference.txt`, set `FLORABOT_MODEL_PATH` (or place `flora_bot_best.pt` in `backend/models/`), then authenticate and use `GET /api/inference/status` and `POST /api/detections/infer?plant_id=<optional-id>` with the image bytes as the request body and its image MIME type as `Content-Type`. The uploaded image is processed in memory and not stored. When the model or runtime is unavailable, status reports unavailable and the inference request returns 503; no example prediction is written to PostgreSQL.

## Authentication and access

`POST /api/auth/register` creates a password-hashed Operator and returns a bearer token. `POST /api/auth/login` accepts email/password and returns a JWT. Send it as `Authorization: Bearer <token>`. Authenticated operators can read and submit crop/device/event records; deleting plants requires Admin. Provision the first Admin from a trusted shell before exposing registration: `python -m app.bootstrap_admin`. It only works while the users table is empty and prompts securely for the password. There are no seeded accounts or default passwords; public registration always creates Operators.

Passwords use Argon2id via pwdlib. JWT signing uses `SECRET_KEY`; tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`.

## Database tables

- `users`: unique email, Argon2 password hash, Admin/Operator role.
- `plants`: crop metadata and optional coordinates/status/last-event times.
- `disease_detections`: supported class, confidence, confidence status, inference reference, optional plant/GPS/model version, detection time.
- `sensor_readings`: extensible sensor type/value/unit with robot and event time.
- `watering_events`: actual event times, duration, optional measured water, trigger and moisture observations.
- `robot_telemetry`: timestamped actual robot state, movement, location and optional battery/tank measurements.
- `alerts`: event-linked operational alerts and read state.

Foreign keys preserve optional plant associations and indexes support common time, robot, and lookup filters. Migration `0001_initial` creates the initial model schema.

## API overview

All routes below are under `/api` and require bearer auth except registration/login:

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Register Operator |
| POST | `/auth/login` | Issue access token |
| GET | `/auth/me` | Current account |
| GET, POST | `/plants` | List/register plants |
| GET, PUT, DELETE | `/plants/{id}` | Read/update/delete plant (Admin for delete) |
| POST | `/detections` | Store inference result and event alert |
| GET | `/detections`, `/detections/{id}` | Read detections |
| GET | `/inference/status` | Check optional local classifier availability |
| POST | `/detections/infer` | Run configured classifier on an uploaded image and persist its actual result |
| POST | `/sensors/readings` | Store a timestamped sensor reading |
| GET | `/sensors/latest`, `/sensors/history` | Query readings |
| POST | `/robot/telemetry` | Store actual robot telemetry |
| GET | `/robot/status` | Latest received telemetry per robot |
| POST | `/watering` | Record completed/observed watering |
| GET | `/watering/history` | Query watering events |
| GET | `/alerts` | Read alerts (optional `unread_only=true`) |
| PUT | `/alerts/{id}/read` | Mark alert as read |
| GET | `/dashboard/summary` | Counts and latest stored records |

Timestamps should be ISO 8601 with timezone, preferably UTC. List endpoints have bounded `limit` parameters. Sensor types are open-ended; common percentage values and temperature get range checks. New sensor types can be added without a schema migration. No current sensor/robot value is filled in when absent; a robot with no telemetry does not appear in `/robot/status`, and empty lists/counts reflect the actual database.

Example device submission (after obtaining a token):

```json
{
  "robot_id": "<device-configured-id>",
  "sensor_type": "soil_moisture",
  "value": 0,
  "unit": "percent",
  "recorded_at": "<device timestamp in ISO 8601>"
}
```

Replace the illustrative strings and value with values measured by the device; zero is a valid reading only when actually measured. Do not send placeholder measurements.

## React and device integration

React can use the bearer-protected REST API and render empty arrays/null latest timestamps as “No data available.” Configure the browser origins in `ALLOWED_ORIGINS`. Devices should use the same API over a secured network, authenticate with deployment-managed accounts/tokens, send monotonically timestamped events where possible, and retry transient failures with an idempotency strategy added at the integration boundary if duplicate delivery is possible. WebSockets/event streaming are not enabled yet; the persisted timestamped REST API is the current integration contract.

## Implemented and planned

Implemented: PostgreSQL-oriented relational schema, Alembic baseline, JWT authentication, role model, REST routes, request validation, disease-class allowlist, event-based alerts, CORS configuration, optional local image-classifier inference, and tests using isolated in-memory SQLite. Remaining hardware work: device identity/provisioning and token lifecycle, TLS/network deployment, ESP32/Raspberry Pi client retry/idempotency, physical sensor calibration and units, camera/image capture/storage policy, irrigation controller integration, offline detection policy, and optional WebSocket dashboard updates. No device integration is claimed until those clients are connected and sending actual measurements.

## Tests

Run from `backend`:

```powershell
pytest
```

Tests create isolated SQLite schemas and records only inside the test database. They do not add production or PostgreSQL data.
