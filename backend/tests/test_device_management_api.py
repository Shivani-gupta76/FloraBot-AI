from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.models import Device
from app.services.device_auth import hash_device_token


def _plant_id(client, auth):
    response = client.post("/api/plants", headers=auth, json={"crop_type": "Tomato"})
    assert response.status_code == 201
    return response.json()["id"]


def _register_device(client, admin_auth, plant_id, identifier="camera-api-001"):
    return client.post(
        "/api/devices",
        headers=admin_auth,
        json={"device_identifier": identifier, "device_name": "Field camera", "plant_id": plant_id},
    )


def test_admin_can_register_device_and_raw_credential_is_returned_once(client, auth, admin_auth, isolated_session_factory):
    plant_id = _plant_id(client, auth)
    response = _register_device(client, admin_auth, plant_id)

    assert response.status_code == 201
    body = response.json()
    token = body["device_token"]
    assert body["plant_id"] == plant_id
    assert body["device_identifier"] == "camera-api-001"
    assert len(token) >= 40

    with isolated_session_factory() as db:
        device = db.get(Device, body["id"])
        assert device.credential_hash == hash_device_token(token)
        assert token != device.credential_hash

    listed = client.get(f"/api/devices/{body['id']}", headers=auth)
    assert listed.status_code == 200
    assert "credential_hash" not in listed.json()
    assert "device_token" not in listed.json()
    assert "credential_revoked_at" not in listed.json()


def test_non_admin_cannot_register_device(client, auth):
    plant_id = _plant_id(client, auth)
    response = client.post(
        "/api/devices",
        headers=auth,
        json={"device_identifier": "operator-camera", "device_name": "No access", "plant_id": plant_id},
    )
    assert response.status_code == 403


def test_registration_rejects_missing_plant(client, admin_auth):
    response = _register_device(client, admin_auth, 987654)
    assert response.status_code == 404


def test_registration_rejects_duplicate_device_identifier(client, auth, admin_auth):
    plant_id = _plant_id(client, auth)
    assert _register_device(client, admin_auth, plant_id).status_code == 201
    duplicate = _register_device(client, admin_auth, plant_id)
    assert duplicate.status_code == 409


def test_valid_device_token_authenticates_and_heartbeat_updates_server_time(client, auth, admin_auth, isolated_session_factory):
    plant_id = _plant_id(client, auth)
    registered = _register_device(client, admin_auth, plant_id).json()
    before = datetime.now(timezone.utc)

    heartbeat = client.post("/api/device/heartbeat", headers={"X-Device-Token": registered["device_token"]})

    after = datetime.now(timezone.utc)
    assert heartbeat.status_code == 200
    payload = heartbeat.json()
    assert payload["device_id"] == registered["id"]
    assert payload["online"] is True
    observed = datetime.fromisoformat(payload["last_seen_at"].replace("Z", "+00:00"))
    assert before <= observed <= after
    with isolated_session_factory() as db:
        assert db.get(Device, registered["id"]).last_seen_at is not None


def test_invalid_device_credential_is_rejected(client):
    credential = "not-a-valid-device-credential"
    response = client.post("/api/device/heartbeat", headers={"X-Device-Token": credential})
    assert response.status_code == 401
    assert credential not in response.text


def test_disabled_device_cannot_authenticate(client, auth, admin_auth):
    plant_id = _plant_id(client, auth)
    registered = _register_device(client, admin_auth, plant_id).json()
    update = client.patch(f"/api/devices/{registered['id']}", headers=admin_auth, json={"enabled": False})
    assert update.status_code == 200 and update.json()["online"] is False
    heartbeat = client.post("/api/device/heartbeat", headers={"X-Device-Token": registered["device_token"]})
    assert heartbeat.status_code == 401


def test_online_offline_is_derived_from_configured_heartbeat_timeout(client, auth, admin_auth, isolated_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "device_heartbeat_timeout_seconds", 60)
    plant_id = _plant_id(client, auth)
    registered = _register_device(client, admin_auth, plant_id).json()
    now = datetime.now(timezone.utc)
    with isolated_session_factory() as db:
        device = db.get(Device, registered["id"])
        device.last_seen_at = now - timedelta(seconds=30)
        db.commit()
    assert client.get(f"/api/devices/{registered['id']}", headers=auth).json()["online"] is True

    with isolated_session_factory() as db:
        device = db.get(Device, registered["id"])
        device.last_seen_at = now - timedelta(seconds=61)
        db.commit()
    assert client.get(f"/api/devices/{registered['id']}", headers=auth).json()["online"] is False


def test_device_authentication_is_scoped_to_credentialed_device(client, auth, admin_auth, isolated_session_factory):
    plant_id = _plant_id(client, auth)
    first = _register_device(client, admin_auth, plant_id, "camera-one").json()
    second = _register_device(client, admin_auth, plant_id, "camera-two").json()

    response = client.post("/api/device/heartbeat", headers={"X-Device-Token": first["device_token"]})

    assert response.status_code == 200 and response.json()["device_id"] == first["id"]
    with isolated_session_factory() as db:
        first_row = db.get(Device, first["id"])
        second_row = db.get(Device, second["id"])
        assert first_row.last_seen_at is not None
        assert second_row.last_seen_at is None


def test_credential_rotation_returns_new_token_once_and_invalidates_old_token(client, auth, admin_auth, isolated_session_factory):
    plant_id = _plant_id(client, auth)
    registered = _register_device(client, admin_auth, plant_id).json()
    rotated = client.post(f"/api/devices/{registered['id']}/credentials/rotate", headers=admin_auth)

    assert rotated.status_code == 200
    body = rotated.json()
    new_token = body["device_token"]
    assert new_token != registered["device_token"]
    assert body["credential_version"] == 2
    assert "credential_hash" not in body
    old_auth = client.post("/api/device/heartbeat", headers={"X-Device-Token": registered["device_token"]})
    new_auth = client.post("/api/device/heartbeat", headers={"X-Device-Token": new_token})
    assert old_auth.status_code == 401
    assert new_auth.status_code == 200
    with isolated_session_factory() as db:
        device = db.get(Device, registered["id"])
        assert device.credential_hash == hash_device_token(new_token)
        assert new_token != device.credential_hash


def test_revoked_device_credential_is_rejected(client, auth, admin_auth):
    plant_id = _plant_id(client, auth)
    registered = _register_device(client, admin_auth, plant_id).json()
    revoked = client.post(f"/api/devices/{registered['id']}/credentials/revoke", headers=admin_auth)
    assert revoked.status_code == 200
    assert revoked.json()["device_id"] == registered["id"]
    heartbeat = client.post("/api/device/heartbeat", headers={"X-Device-Token": registered["device_token"]})
    assert heartbeat.status_code == 401


def test_device_listing_requires_user_auth_and_never_exposes_credentials(client, auth, admin_auth):
    plant_id = _plant_id(client, auth)
    _register_device(client, admin_auth, plant_id)
    assert client.get("/api/devices").status_code == 401
    response = client.get("/api/devices", headers=auth)
    assert response.status_code == 200
    item = response.json()[0]
    assert "credential_hash" not in item
    assert "device_token" not in item
