# ESP32-CAM disease image upload

This endpoint accepts JPEG bytes from the ESP32-CAM, authenticates with the existing configured camera token, runs the existing YOLO classification service, and persists the detection and any alert. A confirmed high-confidence disease may queue an LED2 desired-state command for an enabled registered device associated with the configured plant. The backend does not call hardware or confirm an electrical LED state.

## Backend configuration

Set both variables in the backend's environment configuration before starting FastAPI:

```dotenv
FLORABOT_CAMERA_DEVICE_TOKEN=<unique-long-random-device-token>
FLORABOT_CAMERA_PLANT_ID=<existing-plant-id>
```

Use a unique high-entropy token for this camera, provision the same value into the ESP32 firmware through its private configuration, and keep it out of source control, serial output, HTTP responses, and logs. Do not reuse a user password or JWT. The plant ID must already exist; the device cannot choose a different plant in its request. Restart the backend after changing its environment. Until the token and plant ID are configured, uploads fail closed with `503`.

Use HTTPS when the Wi-Fi network is not trusted. The token is sent in an HTTP header and plain HTTP does not encrypt it.

## HTTP contract

- **Backend URL:** `http://<backend-host>:<port>/api/device/camera/upload` on a trusted development/LAN network, or the corresponding `https://` URL when TLS is configured.
- **Method:** `POST`
- **Headers:**
  - `X-Device-Token: <configured camera token>`
  - `Content-Type: image/jpeg`
  - `Idempotency-Key: <capture-id>` (optional, 1–128 characters)
- **Body:** Raw JPEG file bytes. Do not send multipart form data or Base64 text.
- **Maximum size:** 10 MiB (10,485,760 bytes).
- **Plant association:** Always the configured `FLORABOT_CAMERA_PLANT_ID`; no client-supplied plant ID is accepted.
- **Success:** `201 Created`

When `Idempotency-Key` is supplied, use the same key for every retry of one captured JPEG. For the configured plant, the first successful request returns `201`; a retry with the same key and identical JPEG bytes returns the saved detection/alert with `200` without rerunning inference or creating a second detection/alert. Reusing a key with different image bytes returns `409`. The key is associated with a SHA-256 image digest; image bytes are not stored. Without this optional header, legacy behavior remains: each successful request creates a detection record.

Example success response:

```json
{
  "detection_id": 42,
  "plant_id": 1,
  "predicted_class": "Tomato_Early_Blight",
  "confidence": 0.91,
  "confidence_status": "HIGH_CONFIDENCE",
  "model_version": "flora_bot_best",
  "detected_at": "2026-11-01T10:00:00Z",
  "alert": {
    "id": 17,
    "alert_type": "DISEASE_DETECTED",
    "message": "Disease class reported by inference service",
    "created_at": "2026-11-01T10:00:00Z"
  }
}
```

`alert` is `null` when existing detection rules do not create an alert (for example, a high-confidence healthy classification). Low-confidence/review and disease classes return the alert created by the existing logic. High-confidence disease results queue LED2 `ON`; a high-confidence healthy result queues LED2 `OFF` only when it follows an active disease alert for that plant. Uncertain and review-required results do not change LED2. This decision uses existing confidence statuses and does not add a confidence threshold.

## Error responses

- `401 Unauthorized`: missing or invalid `X-Device-Token`.
- `413 Payload Too Large`: request exceeds the 10 MiB limit.
- `415 Unsupported Media Type`: `Content-Type` is not `image/jpeg`.
- `422 Unprocessable Entity`: empty, malformed, non-JPEG image, or image exceeding the 25-million-pixel decoded limit.
- `409 Conflict`: an idempotency key was reused with different image bytes.
- `503 Service Unavailable`: device token or plant ID is not configured, or inference is unavailable.
- `404 Not Found`: configured plant ID does not identify an existing plant.

Error bodies use FastAPI's standard JSON `detail` field. Device tokens, image bytes and image digests are not included in application logs or responses. The camera endpoint uses its configured shared token; registered-device credential rotation/revocation does not change this existing camera-upload credential.
