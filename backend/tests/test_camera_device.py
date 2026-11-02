from io import BytesIO
import hashlib

from PIL import Image
from pydantic import SecretStr

from app.api import routes
from app.services.inference import MAX_IMAGE_BYTES

DEVICE_TOKEN = "test-only-camera-device-token"


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (24, 24), color=(36, 128, 56))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def _configured_camera(client, auth, monkeypatch) -> int:
    plant = client.post("/api/plants", headers=auth, json={"crop_type": "Tomato"}).json()
    monkeypatch.setattr(routes.settings, "camera_device_token", SecretStr(DEVICE_TOKEN))
    monkeypatch.setattr(routes.settings, "camera_plant_id", plant["id"])
    return plant["id"]


def _upload(client, content: bytes, token: str | None = DEVICE_TOKEN, content_type: str = "image/jpeg"):
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["X-Device-Token"] = token
    return client.post("/api/device/camera/upload", headers=headers, content=content)


def test_camera_upload_saves_detection_and_returns_disease_alert(client, auth, monkeypatch):
    plant_id = _configured_camera(client, auth, monkeypatch)
    monkeypatch.setattr(routes, "classify_image", lambda _image: {
        "class_name": "Tomato_Early_Blight",
        "confidence": 0.91,
        "confidence_status": "HIGH_CONFIDENCE",
        "model_version": "test-model",
    })

    response = _upload(client, _jpeg_bytes())

    assert response.status_code == 201
    payload = response.json()
    assert payload["plant_id"] == plant_id
    assert payload["predicted_class"] == "Tomato_Early_Blight"
    assert payload["confidence"] == 0.91
    assert payload["confidence_status"] == "HIGH_CONFIDENCE"
    assert payload["detection_id"] > 0
    assert payload["alert"]["alert_type"] == "DISEASE_DETECTED"
    assert payload["alert"]["id"] > 0

    detections = client.get("/api/detections", headers=auth).json()
    alerts = client.get("/api/alerts", headers=auth).json()
    assert len(detections) == 1 and detections[0]["id"] == payload["detection_id"]
    assert len(alerts) == 1 and alerts[0]["id"] == payload["alert"]["id"]


def test_camera_upload_rejects_invalid_image_without_records(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    response = _upload(client, b"not a valid jpeg")
    assert response.status_code == 422
    assert client.get("/api/detections", headers=auth).json() == []
    assert client.get("/api/alerts", headers=auth).json() == []


def test_camera_upload_requires_device_token(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    response = _upload(client, _jpeg_bytes(), token=None)
    assert response.status_code == 401


def test_camera_upload_rejects_invalid_device_token(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    response = _upload(client, _jpeg_bytes(), token="wrong-device-token")
    assert response.status_code == 401


def test_camera_upload_rejects_oversized_image(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    response = _upload(client, b"x" * (MAX_IMAGE_BYTES + 1))
    assert response.status_code == 413
    assert client.get("/api/detections", headers=auth).json() == []
    assert client.get("/api/alerts", headers=auth).json() == []


def test_camera_upload_requires_jpeg_content_type(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    response = _upload(client, _jpeg_bytes(), content_type="image/png")
    assert response.status_code == 415


def test_camera_idempotency_key_returns_prior_result_without_duplicate_records(client, auth, monkeypatch, isolated_session_factory):
    _configured_camera(client, auth, monkeypatch)
    calls = []

    def classify(image):
        calls.append(image)
        return {
            "class_name": "Tomato_Early_Blight",
            "confidence": 0.91,
            "confidence_status": "HIGH_CONFIDENCE",
            "model_version": "test-model",
        }

    monkeypatch.setattr(routes, "classify_image", classify)
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "image/jpeg", "Idempotency-Key": "capture-0001"}
    first = client.post("/api/device/camera/upload", headers=headers, content=_jpeg_bytes())
    retry = client.post("/api/device/camera/upload", headers=headers, content=_jpeg_bytes())

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert len(calls) == 1
    assert len(client.get("/api/detections", headers=auth).json()) == 1
    assert len(client.get("/api/alerts", headers=auth).json()) == 1
    from app.db.models import CameraUploadRequest
    with isolated_session_factory() as db:
        upload = db.query(CameraUploadRequest).one()
        assert upload.image_sha256 == hashlib.sha256(_jpeg_bytes()).hexdigest()
        assert upload.idempotency_key == "capture-0001"


def test_camera_idempotency_key_rejects_a_different_image(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    monkeypatch.setattr(routes, "classify_image", lambda _image: {
        "class_name": "Tomato_Early_Blight",
        "confidence": 0.91,
        "confidence_status": "HIGH_CONFIDENCE",
        "model_version": "test-model",
    })
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "image/jpeg", "Idempotency-Key": "capture-0002"}
    first = client.post("/api/device/camera/upload", headers=headers, content=_jpeg_bytes())
    different = Image.new("RGB", (24, 24), color=(180, 20, 20))
    output = BytesIO()
    different.save(output, format="JPEG")
    conflict = client.post("/api/device/camera/upload", headers=headers, content=output.getvalue())

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert len(client.get("/api/detections", headers=auth).json()) == 1


def test_camera_upload_rejects_images_over_decoded_pixel_limit(client, auth, monkeypatch):
    _configured_camera(client, auth, monkeypatch)
    large_image = Image.new("L", (5001, 5000), color=1)
    output = BytesIO()
    large_image.save(output, format="JPEG", quality=20)
    response = _upload(client, output.getvalue())
    assert response.status_code == 422
    assert client.get("/api/detections", headers=auth).json() == []
