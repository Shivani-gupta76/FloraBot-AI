from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.models import Device, DeviceCommand, DeviceCommandStatus, Plant
from app.services.device_commands import poll_device_command


def _plant(client, auth, crop="Tomato"):
    response = client.post("/api/plants", headers=auth, json={"crop_type": crop})
    assert response.status_code == 201
    return response.json()["id"]


def _device(client, admin_auth, plant_id, identifier="commands-camera"):
    response = client.post(
        "/api/devices",
        headers=admin_auth,
        json={"device_identifier": identifier, "device_name": "Command camera", "plant_id": plant_id},
    )
    assert response.status_code == 201
    return response.json()


def _create_command(client, admin_auth, device_id, channel="LED1", state="ON", key="request-1", source=None):
    source = source or ("WATERING_ASSISTANT" if channel == "LED1" else "DISEASE_DETECTION")
    return client.post(
        f"/api/devices/{device_id}/commands",
        headers=admin_auth,
        json={
            "led_channel": channel,
            "desired_state": state,
            "source": source,
            "reason": "Approved workflow decision",
            "idempotency_key": key,
        },
    )


def test_commands_require_admin_and_preserve_independent_channels(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    device = _device(client, admin_auth, plant_id)
    assert _create_command(client, auth, device["id"]).status_code == 403
    first = _create_command(client, admin_auth, device["id"]).json()
    second = _create_command(client, admin_auth, device["id"], "LED2", "OFF", "request-2").json()
    assert (first["led_channel"], first["desired_state"]) == ("LED1", "ON")
    assert (second["led_channel"], second["desired_state"]) == ("LED2", "OFF")
    assert first["status"] == second["status"] == "PENDING"


def test_command_rejects_invalid_channel_state_and_cross_channel_source(client, auth, admin_auth):
    device = _device(client, admin_auth, _plant(client, auth))
    assert _create_command(client, admin_auth, device["id"], channel="LED3").status_code == 422
    assert _create_command(client, admin_auth, device["id"], state="TOGGLE").status_code == 422
    assert _create_command(client, admin_auth, device["id"], source="DISEASE_DETECTION").status_code == 422


def test_command_idempotency_returns_existing_for_same_payload_and_conflicts_for_different(client, auth, admin_auth):
    device = _device(client, admin_auth, _plant(client, auth))
    first = _create_command(client, admin_auth, device["id"], key="retry-key")
    retry = _create_command(client, admin_auth, device["id"], key="retry-key")
    conflict = _create_command(client, admin_auth, device["id"], state="OFF", key="retry-key")
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json()["command_id"] == first.json()["command_id"]
    assert conflict.status_code == 409


def test_disabled_device_cannot_receive_new_commands(client, auth, admin_auth):
    device = _device(client, admin_auth, _plant(client, auth))
    client.patch(f"/api/devices/{device['id']}", headers=admin_auth, json={"enabled": False})
    assert _create_command(client, admin_auth, device["id"]).status_code == 409


def test_device_poll_claims_oldest_once_and_isolates_other_devices(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    first = _device(client, admin_auth, plant_id, "poll-one")
    second = _device(client, admin_auth, plant_id, "poll-two")
    command = _create_command(client, admin_auth, first["id"]).json()
    second_poll = client.post("/api/device/commands/poll", headers={"X-Device-Token": second["device_token"]})
    first_poll = client.post("/api/device/commands/poll", headers={"X-Device-Token": first["device_token"]})
    repeated = client.post("/api/device/commands/poll", headers={"X-Device-Token": first["device_token"]})
    assert second_poll.status_code == first_poll.status_code == repeated.status_code == 200
    assert second_poll.json() == {"command": None}
    assert first_poll.json()["command"]["command_id"] == command["command_id"]
    assert first_poll.json()["command"]["attempt_count"] == 1
    assert repeated.json() == {"command": None}


def test_poll_requires_registered_device_credential(client):
    assert client.post("/api/device/commands/poll").status_code == 401
    assert client.post("/api/device/commands/poll", headers={"X-Device-Token": "bad-token"}).status_code == 401


def test_expired_lease_is_retried_then_fails_at_attempt_limit(db_session, monkeypatch):
    from app.db.models import LedChannel, LedDesiredState

    monkeypatch.setattr(settings, "device_command_lease_seconds", 10)
    monkeypatch.setattr(settings, "device_command_max_attempts", 2)
    plant = Plant(crop_type="Tomato")
    db_session.add(plant)
    db_session.flush()
    device = Device(device_identifier="lease-device", device_name="Lease", plant_id=plant.id, credential_hash="hash")
    db_session.add(device)
    db_session.flush()
    now = datetime.now(timezone.utc)
    command = DeviceCommand(
        device_id=device.id,
        plant_id=plant.id,
        led_channel=LedChannel.LED1,
        desired_state=LedDesiredState.ON,
        command_source="WATERING_ASSISTANT",
        reason="test",
        status=DeviceCommandStatus.PENDING,
        idempotency_key="lease-test",
        attempt_count=0,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    db_session.add(command)
    db_session.commit()
    assert poll_device_command(db_session, device, now) is not None
    assert poll_device_command(db_session, device, now + timedelta(seconds=11)).attempt_count == 2
    assert poll_device_command(db_session, device, now + timedelta(seconds=22)) is None
    db_session.refresh(command)
    assert command.status == DeviceCommandStatus.FAILED
    assert command.failure_code == "DELIVERY_RETRY_LIMIT"


def test_expired_pending_command_is_not_delivered(db_session):
    from app.db.models import LedChannel, LedDesiredState

    plant = Plant(crop_type="Tomato")
    db_session.add(plant)
    db_session.flush()
    device = Device(device_identifier="expired-device", device_name="Expired", plant_id=plant.id, credential_hash="hash")
    db_session.add(device)
    db_session.flush()
    now = datetime.now(timezone.utc)
    command = DeviceCommand(
        device_id=device.id,
        plant_id=plant.id,
        led_channel=LedChannel.LED2,
        desired_state=LedDesiredState.OFF,
        command_source="DISEASE_DETECTION",
        reason="test",
        status=DeviceCommandStatus.PENDING,
        idempotency_key="expired-test",
        attempt_count=0,
        created_at=now - timedelta(minutes=2),
        expires_at=now - timedelta(seconds=1),
    )
    db_session.add(command)
    db_session.commit()
    assert poll_device_command(db_session, device, now) is None
    db_session.refresh(command)
    assert command.status == DeviceCommandStatus.EXPIRED


def test_successful_and_failed_acknowledgements_are_safe_and_idempotent(client, auth, admin_auth):
    device = _device(client, admin_auth, _plant(client, auth))
    token = {"X-Device-Token": device["device_token"]}
    created = _create_command(client, admin_auth, device["id"]).json()
    assert client.post("/api/device/commands/poll", headers=token).status_code == 200
    ack_url = f"/api/device/commands/{created['command_id']}/ack"
    success = client.post(ack_url, headers=token, json={"success": True})
    duplicate = client.post(ack_url, headers=token, json={"success": True})
    conflict = client.post(ack_url, headers=token, json={"success": False, "failure_code": "DEVICE_ERROR"})
    assert success.status_code == duplicate.status_code == 200
    assert success.json()["status"] == "ACKNOWLEDGED"
    assert conflict.status_code == 409

    failed = _create_command(client, admin_auth, device["id"], channel="LED2", key="failed-key").json()
    client.post("/api/device/commands/poll", headers=token)
    failed_ack_url = f"/api/device/commands/{failed['command_id']}/ack"
    failure = client.post(failed_ack_url, headers=token, json={"success": False, "failure_code": "HARDWARE_ERROR"})
    assert failure.status_code == 200
    assert failure.json()["status"] == "FAILED"
    assert failure.json()["failure_detail"] == "Device reported a hardware fault."


def test_ack_requires_delivery_and_device_ownership(client, auth, admin_auth):
    plant_id = _plant(client, auth)
    first = _device(client, admin_auth, plant_id, "ack-first")
    second = _device(client, admin_auth, plant_id, "ack-second")
    command = _create_command(client, admin_auth, first["id"]).json()
    url = f"/api/device/commands/{command['command_id']}/ack"
    assert client.post(url, headers={"X-Device-Token": first["device_token"]}, json={"success": True}).status_code == 409
    assert client.post("/api/device/commands/poll", headers={"X-Device-Token": first["device_token"]}).status_code == 200
    assert client.post(url, headers={"X-Device-Token": second["device_token"]}, json={"success": True}).status_code == 404


def test_history_is_authorized_filtered_paginated_and_credential_free(client, auth, admin_auth):
    device = _device(client, admin_auth, _plant(client, auth))
    assert client.get(f"/api/devices/{device['id']}/commands").status_code == 401
    assert client.get(f"/api/devices/{device['id']}/commands", headers=auth).status_code == 403
    _create_command(client, admin_auth, device["id"], key="history-one")
    _create_command(client, admin_auth, device["id"], channel="LED2", key="history-two")
    page = client.get(f"/api/devices/{device['id']}/commands?limit=1&led_channel=LED2", headers=admin_auth)
    assert page.status_code == 200 and len(page.json()) == 1
    item = page.json()[0]
    assert item["led_channel"] == "LED2"
    assert "credential_hash" not in item and "device_token" not in item
    paged = client.get(f"/api/devices/{device['id']}/commands?limit=1&offset=1", headers=admin_auth)
    assert paged.status_code == 200 and len(paged.json()) == 1
