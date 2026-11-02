from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from app.api import routes
from app.db.models import DeviceCommand


def _plant(client, auth):
    response = client.post("/api/plants", headers=auth, json={"crop_type": "Tomato"})
    assert response.status_code == 201
    return response.json()["id"]


def _device(client, admin_auth, plant_id):
    response = client.post(
        "/api/devices",
        headers=admin_auth,
        json={"device_identifier": "disease-led2-camera", "device_name": "Disease camera", "plant_id": plant_id},
    )
    assert response.status_code == 201
    return response.json()


def _detection(client, auth, plant_id, class_name, confidence_status="HIGH_CONFIDENCE"):
    return client.post(
        "/api/detections",
        headers=auth,
        json={
            "plant_id": plant_id,
            "class_name": class_name,
            "confidence": 0.93,
            "confidence_status": confidence_status,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "model_version": "test-model",
        },
    )


def _commands(client, admin_auth, device_id):
    response = client.get(f"/api/devices/{device_id}/commands", headers=admin_auth)
    assert response.status_code == 200
    return response.json()


def test_confirmed_disease_creates_led2_on_only(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    response = _detection(client, auth, plant_id, "Tomato_Early_Blight")
    commands = _commands(client, admin_auth, device["id"])

    assert response.status_code == 201
    assert len(commands) == 1
    assert commands[0]["led_channel"] == "LED2"
    assert commands[0]["desired_state"] == "ON"
    assert commands[0]["command_source"] == "DISEASE_DETECTION"


def test_healthy_result_clears_only_an_existing_active_disease_condition(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    assert _detection(client, auth, plant_id, "Tomato_Healthy").status_code == 201
    assert _commands(client, admin_auth, device["id"]) == []

    assert _detection(client, auth, plant_id, "Tomato_Late_Blight").status_code == 201
    assert _detection(client, auth, plant_id, "Tomato_Healthy").status_code == 201
    commands = _commands(client, admin_auth, device["id"])
    assert len(commands) == 2
    assert {item["desired_state"] for item in commands} == {"ON", "OFF"}
    assert all(item["led_channel"] == "LED2" for item in commands)


def test_review_or_uncertain_disease_does_not_activate_led2(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    assert _detection(client, auth, plant_id, "Tomato_Early_Blight", "REVIEW_RECOMMENDED").status_code == 201
    assert _detection(client, auth, plant_id, "Tomato_Late_Blight", "UNCERTAIN").status_code == 201
    assert _commands(client, admin_auth, device["id"]) == []


def test_repeated_camera_uploads_do_not_duplicate_active_led2_on(client, auth, admin_auth, monkeypatch):
    from pydantic import SecretStr

    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    monkeypatch.setattr(routes.settings, "camera_device_token", SecretStr("camera-test-token"))
    monkeypatch.setattr(routes.settings, "camera_plant_id", plant_id)
    monkeypatch.setattr(routes, "classify_image", lambda _image: {
        "class_name": "Tomato_Early_Blight",
        "confidence": 0.91,
        "confidence_status": "HIGH_CONFIDENCE",
        "model_version": "test-model",
    })
    image = Image.new("RGB", (16, 16), color=(30, 120, 40))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    headers = {"X-Device-Token": "camera-test-token", "Content-Type": "image/jpeg"}

    first = client.post("/api/device/camera/upload", headers=headers, content=buffer.getvalue())
    second = client.post("/api/device/camera/upload", headers=headers, content=buffer.getvalue())

    assert first.status_code == second.status_code == 201
    assert first.json()["detection_id"] != second.json()["detection_id"]
    commands = _commands(client, admin_auth, device["id"])
    assert len(commands) == 1 and commands[0]["desired_state"] == "ON"


def test_failed_camera_inference_creates_no_detection_alert_or_led_command(client, auth, admin_auth, monkeypatch):
    from pydantic import SecretStr

    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    monkeypatch.setattr(routes.settings, "camera_device_token", SecretStr("camera-test-token"))
    monkeypatch.setattr(routes.settings, "camera_plant_id", plant_id)
    monkeypatch.setattr(routes, "classify_image", lambda _image: (_ for _ in ()).throw(routes.ModelUnavailable("test unavailable")))
    image = Image.new("RGB", (16, 16), color=(30, 120, 40))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    response = client.post(
        "/api/device/camera/upload",
        headers={"X-Device-Token": "camera-test-token", "Content-Type": "image/jpeg"},
        content=buffer.getvalue(),
    )
    assert response.status_code == 503
    assert client.get("/api/detections", headers=auth).json() == []
    assert client.get("/api/alerts", headers=auth).json() == []
    assert _commands(client, admin_auth, device["id"]) == []


def test_same_detection_processing_is_idempotent(db_session):
    from app.db.models import Device, DiseaseDetection, Plant
    from app.services.disease_commands import enqueue_disease_led2_command

    plant = Plant(crop_type="Tomato")
    db_session.add(plant)
    db_session.flush()
    device = Device(device_identifier="same-detection-device", device_name="Test", plant_id=plant.id, credential_hash="test-hash")
    detection = DiseaseDetection(
        plant_id=plant.id,
        class_name="Tomato_Early_Blight",
        confidence=0.9,
        confidence_status="HIGH_CONFIDENCE",
        detected_at=datetime.now(timezone.utc),
        model_version="test-model",
    )
    db_session.add_all([device, detection])
    db_session.commit()

    assert enqueue_disease_led2_command(db_session, detection, "ON") == 1
    assert enqueue_disease_led2_command(db_session, detection, "ON") == 0
    assert db_session.query(DeviceCommand).count() == 1


def test_command_persistence_failure_keeps_detection_and_alert(client, auth, admin_auth, monkeypatch, caplog):
    from app.services import disease_commands

    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("private database details must not be logged")

    monkeypatch.setattr(disease_commands, "create_device_command", fail_enqueue)
    response = _detection(client, auth, plant_id, "Tomato_Early_Blight")
    assert response.status_code == 201
    assert len(client.get("/api/detections", headers=auth).json()) == 1
    alerts = client.get("/api/alerts", headers=auth).json()
    assert len(alerts) == 1 and alerts[0]["alert_type"] == "DISEASE_DETECTED"
    assert _commands(client, admin_auth, device["id"]) == []
    assert "LED2 command enqueue failed" in caplog.text
    assert "private database details" not in caplog.text
