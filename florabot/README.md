# FloraBOT AI – Visual Plant Care Assistant

See plant stress. Understand plant care.

Upload a plant photo in the FloraBOT chat. An AI model looks for visible water stress, the backend turns that into one of three recommendations, and the ESP32 sets LED1 to match. The chat reports the LED state only after the ESP32 confirms it.

| Recommendation | LED1 |
|---|---|
| `WATERING_RECOMMENDED` | ON command |
| `WATERING_NOT_RECOMMENDED` | OFF command |
| `UNCERTAIN` | no command; LED1 stays as it was |

FloraBOT cannot measure soil moisture from a photo, so it always tells the user to check the soil first.

## Layout

```
backend/    FastAPI app, SQLite, chat page and ESP32 screen (app/static), tests
firmware/   ESP32 Arduino sketch for LED1
context/    project plan and reference material (the zip is someone else's project; do not modify)
```

## Run it

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/) (plain `python -m venv` + `pip` works too).

```sh
cd backend
uv venv -p 3.12 .venv
uv pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --port 8000
```

- Chat: http://localhost:8000
- ESP32 screen: http://localhost:8000/esp32.html

Out of the box the AI is the `mock` provider and the ESP32 is simulated, so everything works without a key or hardware. Run the tests with `.venv/bin/python -m pytest`.

## The chat

- **Analyze My Plant**: attach, drop, paste or (on phones) take a photo. Large photos are shrunk in the browser before upload. A live timeline follows the photo through the disease check and the watering analysis to the ESP32's confirmation, then the result card shows the disease check, the watering recommendation, what the AI saw and the LED line. "Read aloud" speaks the result.
- **Soil check**: after a watering result FloraBOT asks whether the soil is dry or moist and adjusts its advice. This never changes the LED.
- **Plant Care Assistance**: six instant topics, or type any question for an AI answer.
- **Hardware widget** in the header: LED1 as last reported, online status and whether the ESP32 is simulated. It opens a details panel with a link to the ESP32 screen.
- **Open on phone**: a QR code for the same chat on your phone (see below). Light, dark and automatic themes stay in sync across open tabs.
- **AI models** (header, Gemini only): pick the model for the watering check and plant-care answers, and for the plant health review: Gemini Flash-Lite (fastest, the default), Gemini Flash (more thorough, can take a minute or more) or Gemini Pro (needs a paid plan). The choice is saved in the browser and sent with each photo or question; the server only accepts models from its list.

## ESP32: simulated or real

`FLORABOT_DEVICE_MODE` in `backend/.env` picks the ESP32 adapter.

**`dummy` (default)** runs a simulated ESP32 inside the backend. It uses the same command queue as the real board, and the chat always says "simulated ESP32". Open the ESP32 screen next to the chat to watch LED1 and choose how the board behaves:

| Behaviour | What the simulated board does |
|---|---|
| Auto-confirm | sets LED1 and confirms after the response delay |
| Manual | waits for you to press "confirm" or "report failure" |
| Fail commands | reports every command as failed; LED1 stays as it was |
| Offline | stops checking in; commands expire unconfirmed after 30 s |

**`real`** waits for the physical ESP32. Set `FLORABOT_DEVICE_MODE=real` and a `FLORABOT_DEVICE_TOKEN` of 16+ characters (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`), start the server with `--host 0.0.0.0` so the board can reach it, and flash the firmware below. The ESP32 screen then becomes a read-only live monitor.

## Use Gemini

1. Create a free API key at https://aistudio.google.com/apikey.
2. In `backend/.env` set `FLORABOT_VISION_PROVIDER=gemini` and `FLORABOT_GEMINI_API_KEY=<your key>`, then restart the server. Each photo uses two Gemini requests (watering and the health review) and each typed question one; free-tier limits are per model, per minute and per day (see AI Studio's rate-limit page), and daily limits reset at midnight Pacific time.
3. Keep the default `FLORABOT_GEMINI_MODEL=gemini-flash-lite-latest`: it answers in about 2–4 seconds, while `gemini-flash-latest` took 44–90 seconds in testing. Older `gemini-2.5-*` models are not offered to new keys.

Gemini analyses photos and answers the chat's plant-care questions. It only accepts real photos: drawings come back as "no plant detected", which correctly ends as `UNCERTAIN`.

## Open the chat on your phone

Start the server with `--host 0.0.0.0` (allow incoming connections when macOS asks) and choose "Open on phone" in the chat. Scan the QR code with a phone on the same Wi-Fi to take plant photos with its camera. Only do this on a trusted network: there is no login, and the device token travels over plain HTTP.

## Flash the ESP32

1. Install the ESP32 board package and the **ArduinoJson** library (v7) in the Arduino IDE.
2. Copy `firmware/florabot_led1/secrets.example.h` to `secrets.h` in the same folder and fill in Wi-Fi, `SERVER_URL` (`http://<laptop-ip>:8000`; find it with `ipconfig getifaddr en0`), and the same device ID and token as `backend/.env`.
3. Set `LED1_PIN` in `florabot_led1.ino` to your LED's GPIO (2 is the on-board LED on many DevKit boards).
4. Upload and open the Serial Monitor at 115200 baud. You should see a poll every 3 seconds.

## How it works

1. The chat posts the photo to `POST /api/analyses`. The backend checks it is a real JPG/PNG under 10 MB and at least 200×200 pixels, then answers right away with an analysis ID.
2. A background task sends the image to the AI provider. Its JSON is checked by `app/decision.py`, which forces `UNCERTAIN` when no plant is detected, the image is poor, the leaves are not visible, the JSON is invalid, or the provider fails.
3. For a watering decision the backend queues an LED1 command that expires after 30 seconds. A newer analysis replaces an unconfirmed older command.
4. The ESP32 (real or simulated) polls for the command, sets LED1 and acknowledges it. The real board uses `POST /api/device/poll` and `POST /api/device/commands/<id>/ack` with `Authorization: Bearer <token>`.
5. The chat polls `GET /api/analyses/<id>` and shows the confirmed, failed or unconfirmed result. `GET /api/hardware` reports the device, its connection and the last LED1 state it reported.

Photos are never stored. Uploads over 1 MB pass through a temporary file that FastAPI deletes when the request ends. Photo analyses and plant-care questions are limited to `FLORABOT_RATE_LIMIT_PER_MINUTE` per browser.

## Plant health check

Every photo also gets a health check that fills in as it goes:

1. **Initial assessment (local, under a second).** `backend/models/flora_bot_best.pt`, the trained YOLO11n classifier from the FloraBot-AI project (`context/FloraBot-AI.zip`), scores the photo against the 15 conditions it knows on tomato, potato and pepper leaves. It was trained on single leaves against plain backgrounds, so it is often unsure on real-world photos. The chat shows it right away with "Looking into this in more detail…".
2. **Detailed review (AI, a few seconds).** The AI provider looks at the photo with the leaf model's full context: what the model is, its 15 labels, its blind spots and its top scores for this photo. It names a pest or disease only when the signs are clear; for ambiguous signs such as white specks it describes the sign, lists the possible causes and suggests a simple check to tell them apart. It also says whether it agrees with the leaf model. Its verdict replaces the initial one, which stays visible underneath. If the review fails, the chat says the detailed check isn't available.

The health check runs next to the watering decision and never changes it or LED1: the leaf model has no water-stress classes, and the plan keeps disease detection separate. The watering prompt also tells the AI that spots and insects are not water-stress signs.

`FLORABOT_GEMINI_REVIEW_MODEL` picks the review model. In testing (November 2026, free tier), `gemini-flash-lite-latest` reviewed in about 3 seconds and consistently found whiteflies on a test photo; `gemini-flash-latest` took over a minute or timed out; Pro models had no free-tier quota. A slower model only delays the review, never the watering result or LED.

It needs Ultralytics and PyTorch (installed by `requirements.txt`, about 1 GB), and the server takes a few extra seconds to start while the model loads. Ultralytics models are AGPL-3.0 licensed. Set `FLORABOT_DISEASE_CLASSIFIER=mock` to skip the leaf model.

## AI providers

Providers are adapters in `backend/app/vision/`: `mock` and `gemini` today. Each one implements `analyze(image, mime_type) -> str`, which returns the model's raw JSON (it never decides what the LED does), and `answer_question(question) -> str` for plant-care questions. The prompts are in `app/vision/prompt.py`. To add another free model:

1. Add `backend/app/vision/<name>.py` with a class that has a `name`, `analyze` and `answer_question`.
2. Add a `case "<name>":` to `build_provider` in `backend/app/vision/__init__.py` and any settings it needs (such as an API key) to `app/config.py` and `.env.example`.
3. Set `FLORABOT_VISION_PROVIDER=<name>` in `.env`.

The `mock` provider returns `FLORABOT_MOCK_RECOMMENDATION` for every photo after `FLORABOT_MOCK_DELAY_SECONDS`, and the chat labels its results as mock results.
