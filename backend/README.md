# Flora-Bot Crop Care Backend

FastAPI/PostgreSQL API for actual Flora-Bot records. It stores values received from clients and devices; it does not simulate readings, locations, detections, robot state, or watering. The database starts empty.

## Architecture and hardware flow

`ESP32 sensors and irrigation hardware → Raspberry Pi → this FastAPI service → PostgreSQL → React dashboard`

The ESP32/Raspberry Pi sends timestamped sensor readings, robot telemetry, completed watering events, and YOLO11n inference results to the API. The trained `flora_bot_best.pt` file stays on the inference host; this backend validates a result against the model's 15 known class labels and records the submitted prediction and confidence status. An uncertain/review result is stored as such and creates a review alert; it is never represented as a confirmed disease. Confirmed disease alerts can queue LED2 desired-state commands; disease events do not start irrigation. Irrigation control and moisture thresholds belong to robot-side control logic; the API records what happened.

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

For a new, empty database, review the migration history below before applying the schema. Never point migrations at a database until its current revision and a restorable backup have been verified:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive API docs are at `/docs`; OpenAPI JSON is at `/openapi.json`. `/health` checks process availability only. Database connectivity is exercised when an API request queries the database.

Optional leaf-image inference is available when the trained YOLO11n-cls weights and Ultralytics runtime are installed on the backend host. Install `requirements-inference.txt`, set `FLORABOT_MODEL_PATH` (or place `flora_bot_best.pt` in `backend/models/`), then authenticate and use `GET /api/inference/status` and `POST /api/detections/infer?plant_id=<optional-id>` with image bytes as the request body and an image MIME type as `Content-Type`. Images are processed in memory; request size is capped at 10 MiB and decoded size at 25 million pixels. When the model or runtime is unavailable, status reports unavailable and the inference request returns 503.

## Authentication and access

`POST /api/auth/register` creates a password-hashed Operator and returns a bearer token. `POST /api/auth/login` accepts email/password and returns a JWT. Send it as `Authorization: Bearer <token>`. Authenticated operators can read and submit crop/device/event records; deleting plants requires Admin. Provision the first Admin from a trusted shell before exposing registration: `python -m app.bootstrap_admin`. It only works while the users table is empty and prompts securely for the password. There are no seeded accounts or default passwords; public registration always creates Operators.

Passwords use Argon2id via pwdlib. JWT signing uses `SECRET_KEY`; tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`.

## Database tables

- `users`: unique email, Argon2 password hash, Admin/Operator role.
- `plants`: crop metadata and optional coordinates/status/last-event times.
- `disease_detections`: supported class, confidence, confidence status, inference reference, optional plant/GPS/model version, detection time.
- `camera_upload_requests`: optional camera idempotency key and image SHA-256 linked to the persisted detection; image bytes are not stored.
- `sensor_readings`: extensible sensor type/value/unit with robot and event time.
- `watering_events`: actual event times, duration, optional measured water, trigger and moisture observations.
- `robot_telemetry`: timestamped actual robot state, movement, location and optional battery/tank measurements.
- `alerts`: event-linked operational alerts and read state.

Foreign keys preserve plant/device associations and indexes support common time, robot, and lookup filters. Migration `0001_initial` is a legacy baseline that calls `Base.metadata.create_all()` from current ORM metadata; it does not alter existing tables. Its downgrade calls `drop_all()` and must never be used against a database whose data must be preserved. Migrations `0002_devices_and_commands` and `0003_camera_upload_idempotency` create missing objects and skip objects already created by the current-metadata baseline.

## API overview

All routes below are under `/api`. Routes require bearer authentication unless identified as public auth or device-token routes. Device administration is Admin-only; authenticated Operators and Admins can read device status.

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
| POST | `/devices` | Admin registers a device and receives its device token once |
| GET | `/devices`, `/devices/{device_id}` | Authenticated device status and heartbeat-derived online state |
| PATCH | `/devices/{device_id}` | Admin enables or disables a device |
| POST | `/devices/{device_id}/credentials/rotate` | Admin rotates a credential; new token is returned once |
| POST | `/devices/{device_id}/credentials/revoke` | Admin revokes the current device credential |
| POST | `/device/heartbeat` | Device-token-authenticated heartbeat |
| POST | `/device/camera/upload` | Existing camera upload contract; uses its configured camera token |
| POST | `/devices/{device_id}/commands` | Admin creates an idempotent desired-state LED command |
| POST | `/device/commands/poll` | Registered device atomically claims its oldest eligible command |
| POST | `/device/commands/{command_id}/ack` | Registered device acknowledges execution success or failure |
| GET | `/devices/{device_id}/commands` | Admin queries paginated, filterable command history |
| POST | `/sensors/readings` | Store a timestamped sensor reading |
| GET | `/sensors/latest`, `/sensors/history` | Query readings |
| POST | `/robot/telemetry` | Store actual robot telemetry |
| GET | `/robot/status` | Latest received telemetry per robot |
| POST | `/watering` | Record completed/observed watering |
| GET | `/watering/history` | Query watering events |
| GET | `/alerts` | Read alerts (optional `unread_only=true`) |
| PUT | `/alerts/{id}/read` | Mark alert as read |
| GET | `/dashboard/summary` | Counts and latest stored records |

Camera upload accepts the optional `Idempotency-Key` header (1–128 characters). With the header, the same plant/key and same JPEG bytes return the original detection and alert with `200`; reusing the key for different bytes returns `409`. Without the header, legacy behavior remains and each successful upload creates a new detection. The key is bound to a SHA-256 digest; image bytes are not saved. See [`docs/esp32-camera-upload.md`](docs/esp32-camera-upload.md) for the complete contract.

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

React can use the bearer-protected REST API and render empty arrays/null latest timestamps as “No data available.” Configure browser origins in `ALLOWED_ORIGINS`. Device registration returns a high-entropy token once; provision it securely and send it as `X-Device-Token`. Device tokens are stored as SHA-256 verifiers, and `FLORABOT_DEVICE_HEARTBEAT_TIMEOUT_SECONDS` controls online status (default 180 seconds). Device status is visible to authenticated users because this schema does not yet assign user accounts ownership of plants. The existing camera upload endpoint keeps its separate configured token contract.

Command creation and history are Admin-only because user-to-plant ownership is not modeled. Commands are desired states (`ON` or `OFF`), never toggles. LED1 accepts only `WATERING_ASSISTANT` source commands and LED2 only `DISEASE_DETECTION` source commands. A device polls with `POST /api/device/commands/poll` using `X-Device-Token`, then acknowledges the returned UUID at `POST /api/device/commands/{command_id}/ack` with `{"success": true}` or `{"success": false, "failure_code": "HARDWARE_ERROR"}`. Safe failure codes are `DEVICE_ERROR`, `HARDWARE_ERROR`, `EXECUTION_TIMEOUT`, and `UNKNOWN`. Poll responses are empty as `{"command": null}` when nothing is available. Configure `FLORABOT_DEVICE_COMMAND_LEASE_SECONDS` (default 30), `FLORABOT_DEVICE_COMMAND_MAX_ATTEMPTS` (default 3), and `FLORABOT_DEVICE_COMMAND_TTL_SECONDS` (default 300) in the backend environment. A stale lease may be redelivered while the command remains valid and under its retry limit; an expired command is not delivered. Idempotency keys are unique per device; an identical retry returns the existing command, while reusing a key for a different payload returns 409. Delivery cannot guarantee exactly-once execution: device firmware should apply desired states idempotently and acknowledge outcomes. `ACKNOWLEDGED` means the device reported successful execution; without a physical feedback sensor, it does not independently verify the electrical LED state. No command is sent to hardware by the backend itself.

## Implemented and planned

Implemented: PostgreSQL-oriented relational schema, additive device/command migrations, JWT and registered-device authentication, REST routes, request validation, the 15-class allowlist, event alerts, optional local image inference, camera upload idempotency, LED2 disease commands, and isolated SQLite unit/API tests. Remaining hardware work includes firmware polling/acknowledgement, secure token provisioning, TLS deployment, sensor calibration, irrigation controller integration, and physical feedback if electrical LED state must be verified. The camera upload route still uses its separate configured shared token; registered-device rotation/revocation does not rotate that legacy camera token. No physical connection or LED state is claimed by a command acknowledgement.

## Tests

Run from `backend`:

```powershell
pytest
```

Tests create isolated SQLite schemas and records only inside the test database. They do not add production or PostgreSQL data.

Optional PostgreSQL integration tests use only `FLORABOT_TEST_DATABASE_URL`, require a dedicated database name ending in `_test`, create a uniquely named test schema, and retain that schema rather than dropping data. No integration database is selected through `DATABASE_URL` or `.env`. See [`docs/postgresql-integration.md`](docs/postgresql-integration.md).

See [`docs/api-and-operations.md`](docs/api-and-operations.md) for the full API, environment, error and migration reference.

## Migration procedure for an existing database

1. Take and verify a restorable backup before a schema change.
2. Confirm the intended database identity out of band. Do not use the application's `.env` implicitly for a migration review.
3. Inspect `alembic history` and `alembic current` for that target, then compare actual tables and constraints with migrations `0001`–`0003`. Never re-run `0001` manually and never run `alembic downgrade` on a database with retained data.
4. For a database stamped at `0001`, the intended forward operation is `alembic upgrade head`; it adds missing device/command and camera-upload tables and leaves existing data in place. Review generated DDL first.
5. If the existing schema is unversioned or its revision is unclear, stop and prepare a reviewed `alembic stamp` plan only after schema comparison. Do not guess the revision.
6. Apply only after explicit approval for the specific database. This Phase 5 work did not inspect or migrate the configured development database.
