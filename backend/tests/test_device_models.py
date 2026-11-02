from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import (
    Device,
    DeviceCommand,
    DeviceCommandStatus,
    LedChannel,
    LedDesiredState,
    Plant,
)


def _plant(db_session, crop_type="Tomato"):
    plant = Plant(crop_type=crop_type)
    db_session.add(plant)
    db_session.commit()
    db_session.refresh(plant)
    return plant


def _device(db_session, plant, identifier="camera-001", credential_hash=None):
    device = Device(
        device_identifier=identifier,
        device_name="Test camera",
        plant_id=plant.id,
        credential_hash=credential_hash or ("a" * 64),
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


def _command(device, channel, idempotency_key, **overrides):
    now = datetime.now(timezone.utc)
    values = {
        "device_id": device.id,
        "plant_id": device.plant_id,
        "led_channel": channel,
        "desired_state": LedDesiredState.ON,
        "command_source": "WATERING_ASSISTANT" if channel == LedChannel.LED1 else "DISEASE_DETECTION",
        "idempotency_key": idempotency_key,
        "expires_at": now + timedelta(minutes=5),
    }
    values.update(overrides)
    return DeviceCommand(**values)


def test_device_creation_and_plant_relationship(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)

    assert device.id is not None
    assert device.device_identifier == "camera-001"
    assert device.enabled is True
    assert device.credential_hash == "a" * 64
    assert device.plant.id == plant.id
    assert device.created_at is not None
    assert device.updated_at is not None
    assert device.last_seen_at is None


def test_device_identifier_is_unique(db_session):
    plant = _plant(db_session)
    _device(db_session, plant, credential_hash="a" * 64)
    duplicate = Device(
        device_identifier="camera-001",
        device_name="Second camera",
        plant_id=plant.id,
        credential_hash="b" * 64,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_device_enabled_status_and_credential_rotation_fields(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    now = datetime.now(timezone.utc)
    device.enabled = False
    device.credential_hash = "b" * 64
    device.credential_version += 1
    device.credential_rotated_at = now
    db_session.commit()
    db_session.refresh(device)
    assert device.enabled is False
    assert device.credential_version == 2
    assert device.credential_hash == "b" * 64
    assert device.credential_rotated_at is not None

    device.credential_revoked_at = now
    db_session.commit()
    assert device.credential_revoked_at is not None


def test_commands_keep_device_and_plant_association_and_leds_independent(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    led1 = _command(device, LedChannel.LED1, "request-led1")
    led2 = _command(device, LedChannel.LED2, "request-led2", desired_state=LedDesiredState.OFF)
    db_session.add_all([led1, led2])
    db_session.commit()

    assert led1.command_id != led2.command_id
    assert led1.led_channel == LedChannel.LED1 and led1.desired_state == LedDesiredState.ON
    assert led2.led_channel == LedChannel.LED2 and led2.desired_state == LedDesiredState.OFF
    assert led1.status == DeviceCommandStatus.PENDING
    assert led1.device.id == device.id and led1.plant_id == plant.id
    assert led2.device.id == device.id and led2.plant_id == plant.id
    assert led1.attempt_count == 0


def test_command_rejects_a_plant_that_does_not_match_its_device(db_session):
    plant = _plant(db_session, "Tomato")
    other_plant = _plant(db_session, "Pepper")
    device = _device(db_session, plant)
    mismatched = _command(device, LedChannel.LED1, "wrong-plant", plant_id=other_plant.id)
    db_session.add(mismatched)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_command_database_constraint_rejects_cross_led_source(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    invalid = _command(device, LedChannel.LED1, "wrong-channel-source", command_source="DISEASE_DETECTION")
    db_session.add(invalid)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [("led_channel", "LED3"), ("desired_state", "TOGGLE"), ("status", "QUEUED")],
)
def test_command_rejects_invalid_led_values_and_status(db_session, field, value):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    command = _command(device, LedChannel.LED1, f"invalid-{field}")
    setattr(command, field, value)
    db_session.add(command)

    with pytest.raises(StatementError):
        db_session.flush()
    db_session.rollback()


def test_idempotency_key_is_unique_per_device(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    first = _command(device, LedChannel.LED1, "retry-key")
    db_session.add(first)
    db_session.commit()
    duplicate = _command(device, LedChannel.LED2, "retry-key", desired_state=LedDesiredState.OFF)
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_all_command_status_values_are_storable_when_required_fields_exist(db_session):
    plant = _plant(db_session)
    device = _device(db_session, plant)
    now = datetime.now(timezone.utc)
    commands = [
        _command(device, LedChannel.LED1, "status-pending", status=DeviceCommandStatus.PENDING),
        _command(device, LedChannel.LED1, "status-delivered", status=DeviceCommandStatus.DELIVERED, delivered_at=now),
        _command(device, LedChannel.LED2, "status-acknowledged", status=DeviceCommandStatus.ACKNOWLEDGED, delivered_at=now, acknowledged_at=now),
        _command(device, LedChannel.LED2, "status-failed", status=DeviceCommandStatus.FAILED, delivered_at=now, acknowledged_at=now, failure_code="DEVICE_ERROR"),
        _command(device, LedChannel.LED1, "status-expired", status=DeviceCommandStatus.EXPIRED, created_at=now - timedelta(minutes=10), expires_at=now - timedelta(minutes=5)),
    ]
    db_session.add_all(commands)
    db_session.commit()

    assert {command.status for command in commands} == set(DeviceCommandStatus)
