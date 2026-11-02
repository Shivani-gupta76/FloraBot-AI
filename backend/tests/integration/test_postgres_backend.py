"""Opt-in PostgreSQL integration checks against a dedicated disposable database.

Set FLORABOT_TEST_DATABASE_URL in the process environment to a database whose
name ends with ``_test``. These tests create a unique schema and never use the
application's DATABASE_URL or the backend .env file.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4
import os

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models import Alert, AlertType, Device, DeviceCommand, DeviceCommandStatus, DiseaseDetection, Plant
from app.schemas import DeviceCommandCreateIn, DetectionIn
from app.services.device_auth import generate_device_token, hash_device_token
from app.services.device_commands import create_device_command, poll_device_command


@pytest.fixture(scope="module")
def postgres_session_factory():
    url_text = os.environ.get("FLORABOT_TEST_DATABASE_URL")
    if not url_text:
        pytest.skip("FLORABOT_TEST_DATABASE_URL is not configured; PostgreSQL tests were not run.")
    url = make_url(url_text)
    if not url.drivername.startswith("postgresql") or not (url.database or "").lower().endswith("_test"):
        pytest.fail("PostgreSQL tests require a dedicated database name ending in _test.")

    schema = f"florabot_it_{uuid4().hex}"
    control_engine = create_engine(url, poolclass=NullPool)
    try:
        with control_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        control_engine.dispose()

    engine = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()
    # The generated schema is intentionally retained. Dispose the dedicated test
    # database after running this suite; this fixture never drops user data/tables.


def _seed_device(session_factory, identifier: str):
    with session_factory() as db:
        plant = Plant(crop_type="Tomato")
        db.add(plant)
        db.flush()
        device = Device(
            device_identifier=identifier,
            device_name="PostgreSQL integration camera",
            plant_id=plant.id,
            credential_hash=f"hash-{identifier}",
        )
        db.add(device)
        db.commit()
        return device.id, plant.id


def _seed_authenticated_device(session_factory, identifier: str):
    token = generate_device_token()
    with session_factory() as db:
        plant = Plant(crop_type="Tomato")
        db.add(plant)
        db.flush()
        device = Device(
            device_identifier=identifier,
            device_name="PostgreSQL acknowledgement camera",
            plant_id=plant.id,
            credential_hash=hash_device_token(token),
        )
        db.add(device)
        db.commit()
        return device.id, plant.id, token


@contextmanager
def _postgres_api_client(session_factory):
    from app.db.database import get_db
    from app.main import app

    previous_override = app.dependency_overrides.get(get_db)

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def _create_ack_test_command(session_factory, device_id: int, key: str, channel: str):
    with session_factory() as db:
        device = db.get(Device, device_id)
        source = "WATERING_ASSISTANT" if channel == "LED1" else "DISEASE_DETECTION"
        command, created = create_device_command(
            db,
            device,
            DeviceCommandCreateIn(
                led_channel=channel,
                desired_state="ON",
                source=source,
                reason="PostgreSQL acknowledgement integration test",
                idempotency_key=key,
            ),
        )
        assert created
        return command.command_id


def test_postgres_foreign_keys_and_command_constraints(postgres_session_factory):
    factory = postgres_session_factory
    with factory() as db:
        plant = Plant(crop_type="Tomato")
        db.add(plant)
        db.flush()
        device = Device(device_identifier="pg-fk-device", device_name="Camera", plant_id=plant.id, credential_hash="pg-fk-hash")
        db.add(device)
        db.commit()
        assert device.id is not None

        invalid = Device(device_identifier="pg-no-plant", device_name="Bad", plant_id=999999, credential_hash="bad-hash")
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Device).where(Device.device_identifier == "pg-no-plant")) == 0


def test_postgres_concurrent_command_idempotency(postgres_session_factory):
    factory = postgres_session_factory
    device_id, plant_id = _seed_device(factory, "pg-idempotency-device")
    barrier = Barrier(2)
    payload = DeviceCommandCreateIn(
        led_channel="LED1",
        desired_state="ON",
        source="WATERING_ASSISTANT",
        reason="Integration test desired state",
        idempotency_key="same-concurrent-key",
    )

    def create_once():
        with factory() as db:
            device = db.get(Device, device_id)
            barrier.wait()
            command, created = create_device_command(db, device, payload)
            return str(command.command_id), created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _n: create_once(), range(2)))
    assert results[0][0] == results[1][0]
    assert sum(int(created) for _command_id, created in results) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DeviceCommand).where(DeviceCommand.device_id == device_id)) == 1


def test_postgres_concurrent_polling_claims_one_command(postgres_session_factory):
    factory = postgres_session_factory
    device_id, _plant_id = _seed_device(factory, "pg-poll-device")
    with factory() as db:
        device = db.get(Device, device_id)
        command, created = create_device_command(
            db,
            device,
            DeviceCommandCreateIn(
                led_channel="LED2",
                desired_state="ON",
                source="DISEASE_DETECTION",
                reason="Integration polling claim",
                idempotency_key="poll-once",
            ),
        )
        assert created
        command_id = command.command_id

    barrier = Barrier(2)

    def poll_once():
        with factory() as db:
            device = db.get(Device, device_id)
            barrier.wait()
            result = poll_device_command(db, device)
            return None if result is None else result.command_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _n: poll_once(), range(2)))
    assert results.count(command_id) == 1
    assert results.count(None) == 1
    with factory() as db:
        stored = db.get(DeviceCommand, command_id)
        assert stored.status == DeviceCommandStatus.DELIVERED
        assert stored.attempt_count == 1


def test_postgres_detection_alert_and_command_commit_and_rollback(postgres_session_factory):
    factory = postgres_session_factory
    device_id, plant_id = _seed_device(factory, "pg-disease-device")
    from app.api.routes import persist_detection

    with factory() as db:
        detection, alert, created = persist_detection(
            DetectionIn(
                plant_id=plant_id,
                class_name="Tomato_Early_Blight",
                confidence=0.95,
                confidence_status="HIGH_CONFIDENCE",
                detected_at=datetime.now(timezone.utc),
                model_version="integration-test-model",
            ),
            db,
        )
        assert created and alert is not None
        assert alert.alert_type == AlertType.disease_detected
        assert db.scalar(select(func.count()).select_from(DeviceCommand).where(DeviceCommand.device_id == device_id)) == 1

    with factory() as db:
        before = db.scalar(select(func.count()).select_from(DiseaseDetection))
        invalid = DiseaseDetection(
            plant_id=999999,
            class_name="Tomato_Early_Blight",
            confidence=0.9,
            confidence_status="HIGH_CONFIDENCE",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(DiseaseDetection)) == before


def test_postgres_device_command_acknowledgement_success_and_ownership(postgres_session_factory):
    factory = postgres_session_factory
    device_id, _plant_id, device_token = _seed_authenticated_device(factory, f"pg-ack-owner-{uuid4().hex}")
    other_device_id, _other_plant_id, other_token = _seed_authenticated_device(factory, f"pg-ack-other-{uuid4().hex}")
    command_id = _create_ack_test_command(factory, device_id, f"ack-success-{uuid4().hex}", "LED2")

    with _postgres_api_client(factory) as client:
        unauthenticated = client.post(
            f"/api/device/commands/{command_id}/ack",
            json={"success": True},
        )
        invalid_credential = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers={"X-Device-Token": "invalid-test-credential"},
            json={"success": True},
        )
        assert unauthenticated.status_code == 401
        assert invalid_credential.status_code == 401

        owner_headers = {"X-Device-Token": device_token}
        polled = client.post("/api/device/commands/poll", headers=owner_headers)
        assert polled.status_code == 200
        assert polled.json()["command"]["command_id"] == str(command_id)

        not_owner = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers={"X-Device-Token": other_token},
            json={"success": True},
        )
        assert not_owner.status_code == 404
        with factory() as db:
            still_delivered = db.get(DeviceCommand, command_id)
            assert still_delivered.status == DeviceCommandStatus.DELIVERED
            assert still_delivered.acknowledged_at is None

        acknowledged = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers=owner_headers,
            json={"success": True},
        )
        duplicate = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers=owner_headers,
            json={"success": True},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "ACKNOWLEDGED"
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "ACKNOWLEDGED"

    with factory() as db:
        stored = db.get(DeviceCommand, command_id)
        assert stored.device_id == device_id
        assert stored.status == DeviceCommandStatus.ACKNOWLEDGED
        assert stored.delivered_at is not None
        assert stored.acknowledged_at is not None
        assert stored.failure_code is None
        assert stored.failure_detail is None
        assert db.get(Device, other_device_id) is not None


def test_postgres_device_command_acknowledgement_failure_persists_sanitized_result(postgres_session_factory):
    factory = postgres_session_factory
    device_id, _plant_id, device_token = _seed_authenticated_device(factory, f"pg-ack-failed-{uuid4().hex}")
    command_id = _create_ack_test_command(factory, device_id, f"ack-failure-{uuid4().hex}", "LED1")
    headers = {"X-Device-Token": device_token}

    with _postgres_api_client(factory) as client:
        polled = client.post("/api/device/commands/poll", headers=headers)
        assert polled.status_code == 200
        assert polled.json()["command"]["command_id"] == str(command_id)
        failed = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers=headers,
            json={"success": False, "failure_code": "HARDWARE_ERROR"},
        )
        assert failed.status_code == 200
        assert failed.json()["status"] == "FAILED"
        assert failed.json()["failure_code"] == "HARDWARE_ERROR"
        assert failed.json()["failure_detail"] == "Device reported a hardware fault."
        duplicate = client.post(
            f"/api/device/commands/{command_id}/ack",
            headers=headers,
            json={"success": False, "failure_code": "HARDWARE_ERROR"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "FAILED"

    with factory() as db:
        stored = db.get(DeviceCommand, command_id)
        assert stored.device_id == device_id
        assert stored.status == DeviceCommandStatus.FAILED
        assert stored.delivered_at is not None
        assert stored.acknowledged_at is not None
        assert stored.failure_code == "HARDWARE_ERROR"
        assert stored.failure_detail == "Device reported a hardware fault."
