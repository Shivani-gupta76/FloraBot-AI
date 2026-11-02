# Backend API and operations reference

## Environment configuration

Configuration is loaded by `app/core/config.py` from process environment variables, with the backend `.env` file as a local-development fallback. Keep real values in the environment or ignored `.env`; commit placeholder values only.

| Variable | Purpose | Example/Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection | `postgresql+psycopg://<user>:<password>@<host>:<port>/<database>` |
| `SECRET_KEY` | JWT signing key; required to issue/validate tokens | `<long-random-secret>` |
| `ALLOWED_ORIGINS` | Browser origins, comma-separated | `http://localhost:5173` |
| `ENVIRONMENT` | Runtime environment | `development` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | User JWT lifetime | `30` |
| `FLORABOT_MODEL_PATH` | Optional trained YOLO11n-cls checkpoint | `models/flora_bot_best.pt` |
| `FLORABOT_CAMERA_DEVICE_TOKEN` | Existing camera endpoint shared credential | `<unique-random-device-token>` |
| `FLORABOT_CAMERA_PLANT_ID` | Existing plant assigned to camera upload | `<plant-id>` |
| `FLORABOT_DEVICE_HEARTBEAT_TIMEOUT_SECONDS` | Online status window | `180` |
| `FLORABOT_DEVICE_COMMAND_LEASE_SECONDS` | Command lease duration | `30` |
| `FLORABOT_DEVICE_COMMAND_MAX_ATTEMPTS` | Maximum delivery attempts | `3` |
| `FLORABOT_DEVICE_COMMAND_TTL_SECONDS` | Command maximum age | `300` |

The camera upload limit is 10 MiB compressed and 25,000,000 decoded pixels. The image is validated and processed in memory; image bytes are not saved.

## Authentication

- User APIs use `Authorization: Bearer <JWT>`. `POST /api/auth/register` creates an Operator; Admin users are provisioned using `python -m app.bootstrap_admin` before the users table contains accounts.
- Device heartbeat and command APIs use `X-Device-Token` from the registered-device credential store. Device tokens are generated randomly and only SHA-256 verifiers are stored. Rotation invalidates the previous registered-device token; revocation and disabling reject device authentication.
- The existing `POST /api/device/camera/upload` retains its separate `FLORABOT_CAMERA_DEVICE_TOKEN` shared-token contract. It does not use the registered-device credential record, so registered-device rotation/revocation does not revoke this camera credential. Keep it high entropy, private, and restricted to a trusted network; use TLS where credentials could traverse an untrusted network.

## Main route groups

All paths are prefixed with `/api`.

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| POST | `/auth/register`, `/auth/login` | Public | Create Operator / issue JWT |
| GET | `/auth/me` | User | Current user |
| GET, POST | `/plants` | User | List/create plants |
| GET, PUT, DELETE | `/plants/{plant_id}` | User; Admin for delete | Read/update/delete plant |
| GET, POST | `/detections`, `/detections/{detection_id}` | User | Read/save detection results |
| GET | `/inference/status` | User | Local model availability |
| POST | `/detections/infer` | User | Infer and persist one image result |
| POST | `/devices` | Admin | Register device; raw credential returned once |
| GET | `/devices`, `/devices/{device_id}` | User | Device metadata and derived online status |
| PATCH | `/devices/{device_id}` | Admin | Enable/disable device |
| POST | `/devices/{device_id}/credentials/rotate` | Admin | Rotate credential, return new token once |
| POST | `/devices/{device_id}/credentials/revoke` | Admin | Revoke current credential |
| POST | `/device/heartbeat` | Registered device | Update server-side last-seen timestamp |
| POST | `/device/camera/upload` | Configured camera token | JPEG inference, persistence and optional idempotent retry |
| POST | `/devices/{device_id}/commands` | Admin | Create desired-state command |
| POST | `/device/commands/poll` | Registered device | Claim its oldest eligible command |
| POST | `/device/commands/{command_id}/ack` | Registered device | Acknowledge execution result |
| GET | `/devices/{device_id}/commands` | Admin | Filterable paginated command history |
| POST | `/sensors/readings`, `/robot/telemetry`, `/watering` | User | Store actual submitted events |
| GET | `/sensors/latest`, `/sensors/history`, `/robot/status`, `/watering/history` | User | Read submitted events |
| GET | `/alerts`, `/dashboard/summary` | User | Read alerts and summary |
| PUT | `/alerts/{alert_id}/read` | User | Mark alert read |

Admin-only device command creation/history is intentional because plant ownership is not attached to user accounts. Use bounded pagination (`limit`, `offset`); command history supports `led_channel=LED1|LED2` and `status=PENDING|DELIVERED|ACKNOWLEDGED|FAILED|EXPIRED` filters.

## Disease detection and alerts

The allowlist is the model's 15 supported classes in `app/schemas.py`. The inference service uses the model's returned confidence status; this API adds no confidence threshold. A disease alert is created for a confirmed disease result, and review/uncertain classifications create a review alert. Detection and associated alert are committed together.

Only `HIGH_CONFIDENCE` disease results queue an LED2 `ON` desired state. A high-confidence healthy result queues LED2 `OFF` only when the latest decisive high-confidence result for the same plant is a disease with its matching disease alert. Review-required and uncertain results leave LED2 unchanged. Alert `is_read` is not treated as resolution. The current schema has no explicit `resolved_at`; disease-active state is derived from the latest decisive detection. Historical alerts remain in the database. A command persistence failure leaves detection/alert data saved and writes a sanitized error-type log entry.

LED1 is reserved for future `WATERING_ASSISTANT` decisions. LED2 accepts only `DISEASE_DETECTION`. Commands always specify a desired `ON` or `OFF` state and channel. Poll/ack is at-least-once delivery with a lease, retry limit and expiry; it cannot promise exactly-once hardware execution. `ACKNOWLEDGED` means firmware reported success, not that an independent sensor verified electrical state. The backend does not issue network calls to the ESP32 or control LEDs directly.

## Common errors

FastAPI returns validation details under `detail`; the installed validation handler omits submitted values so invalid passwords, tokens, and other inputs are not echoed. Common status classes are:

- `401`: missing/invalid user or device credentials.
- `403`: authenticated user lacks the required role.
- `404`: record does not exist or belongs to another device.
- `409`: duplicate identity/key conflict, invalid command transition, or idempotency key reused for different bytes.
- `413`: image exceeds the compressed request limit.
- `415`: unsupported image content type.
- `422`: invalid request fields or unreadable/oversized decoded image.
- `503`: model/runtime or required camera configuration is unavailable.

No API response includes credential hashes. Application logs must not include request headers, tokens, database URLs, or image bytes.

## Migration safety

Do not modify or manually rerun `0001_initial`. It is a legacy baseline using current ORM metadata with `create_all`; the downgrade calls `drop_all` and is destructive. Revision `0002_devices_and_commands` now checks for existing device tables/indexes because the baseline may already have created them. Revision `0003_camera_upload_idempotency` adds the optional camera retry table and the LED channel/source database constraint, while skipping objects already present from ORM metadata.

For an existing PostgreSQL database, first identify the target explicitly with a process-level `DATABASE_URL`, inspect Alembic revision and actual schema, and verify a restorable backup. Review the generated PostgreSQL DDL before applying `alembic upgrade head`. Do not downgrade a retained database; the historical downgrade functions remove tables. No migration was applied during Phase 5.

## Hardware boundary

Firmware work remains required: securely store the camera/registered-device credential, upload raw JPEG bytes, send an optional stable `Idempotency-Key` per capture, poll commands, apply the exact channel/state idempotently, and acknowledge success/failure using supported codes. The camera shared token remains separately configured from the registered credential lifecycle. TLS and physical LED feedback depend on the deployment/hardware. No hardware connection is claimed.
