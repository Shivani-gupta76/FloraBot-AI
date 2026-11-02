"""Command creation helpers shared by authenticated APIs and future workflows."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Device, DeviceCommand, DeviceCommandStatus
from app.schemas import DeviceCommandCreateIn


class DeviceNotCommandable(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


_SAFE_FAILURE_DETAILS = {
    "DEVICE_ERROR": "Device reported an execution error.",
    "HARDWARE_ERROR": "Device reported a hardware fault.",
    "EXECUTION_TIMEOUT": "Device reported an execution timeout.",
    "UNKNOWN": "Device reported an unspecified failure.",
    "DELIVERY_RETRY_LIMIT": "Delivery lease expired after the maximum attempts.",
}


def safe_failure_detail(code: str) -> str:
    return _SAFE_FAILURE_DETAILS.get(code, "Device command failed.")


def _same_request(command: DeviceCommand, device: Device, data: DeviceCommandCreateIn) -> bool:
    return (
        command.device_id == device.id
        and command.plant_id == device.plant_id
        and command.led_channel.value == data.led_channel
        and command.desired_state.value == data.desired_state
        and command.command_source == data.source
        and command.reason == data.reason
    )


def create_device_command(
    db: Session,
    device: Device,
    data: DeviceCommandCreateIn,
    now: datetime | None = None,
) -> tuple[DeviceCommand, bool]:
    """Create one command or return an identical prior request for safe retries."""
    if not device.enabled or device.credential_revoked_at is not None:
        raise DeviceNotCommandable
    expected_source = "WATERING_ASSISTANT" if data.led_channel == "LED1" else "DISEASE_DETECTION"
    if data.source != expected_source:
        raise ValueError("Command source does not match the reserved LED channel")

    existing = db.scalar(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.idempotency_key == data.idempotency_key,
        )
    )
    if existing is not None:
        if _same_request(existing, device, data):
            return existing, False
        raise IdempotencyConflict

    now = now or datetime.now(timezone.utc)
    command = DeviceCommand(
        device_id=device.id,
        plant_id=device.plant_id,
        led_channel=data.led_channel,
        desired_state=data.desired_state,
        command_source=data.source,
        reason=data.reason,
        status=DeviceCommandStatus.PENDING,
        idempotency_key=data.idempotency_key,
        attempt_count=0,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.device_command_ttl_seconds),
    )
    db.add(command)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # A concurrent request may have inserted the same key after our initial lookup.
        existing = db.scalar(
            select(DeviceCommand).where(
                DeviceCommand.device_id == device.id,
                DeviceCommand.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None and _same_request(existing, device, data):
            return existing, False
        raise IdempotencyConflict from error
    db.refresh(command)
    return command, True


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def poll_device_command(db: Session, device: Device, now: datetime | None = None) -> DeviceCommand | None:
    """Claim the oldest eligible command under a row lock and renew its lease."""
    now = now or datetime.now(timezone.utc)
    lease_seconds = settings.device_command_lease_seconds
    max_attempts = settings.device_command_max_attempts

    # Expiry takes precedence over lease recovery: stale commands cannot outlive their TTL.
    expired = db.scalars(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status.in_([DeviceCommandStatus.PENDING, DeviceCommandStatus.DELIVERED]),
            DeviceCommand.expires_at <= now,
        )
        .with_for_update()
    ).all()
    for command in expired:
        command.status = DeviceCommandStatus.EXPIRED
        command.failure_code = "COMMAND_EXPIRED"
        command.failure_detail = "Command expired before successful acknowledgement."

    exhausted = db.scalars(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status == DeviceCommandStatus.DELIVERED,
            DeviceCommand.expires_at > now,
            DeviceCommand.delivered_at <= now - timedelta(seconds=lease_seconds),
            DeviceCommand.attempt_count >= max_attempts,
        )
        .with_for_update()
    ).all()
    for command in exhausted:
        command.status = DeviceCommandStatus.FAILED
        command.failure_code = "DELIVERY_RETRY_LIMIT"
        command.failure_detail = safe_failure_detail("DELIVERY_RETRY_LIMIT")

    eligible = db.scalar(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.expires_at > now,
            DeviceCommand.attempt_count < max_attempts,
            (
                (DeviceCommand.status == DeviceCommandStatus.PENDING)
                | (
                    (DeviceCommand.status == DeviceCommandStatus.DELIVERED)
                    & (DeviceCommand.delivered_at <= now - timedelta(seconds=lease_seconds))
                )
            ),
        )
        .order_by(DeviceCommand.created_at, DeviceCommand.command_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if eligible is not None:
        eligible.status = DeviceCommandStatus.DELIVERED
        eligible.delivered_at = now
        eligible.attempt_count += 1
    db.commit()
    if eligible is not None:
        db.refresh(eligible)
    return eligible


def acknowledge_device_command(
    db: Session,
    device: Device,
    command_id: UUID,
    success: bool,
    failure_code: str | None = None,
    now: datetime | None = None,
) -> tuple[DeviceCommand, bool]:
    """Apply an acknowledgement; matching duplicates are idempotent."""
    now = now or datetime.now(timezone.utc)
    command = db.scalar(
        select(DeviceCommand)
        .where(DeviceCommand.command_id == command_id, DeviceCommand.device_id == device.id)
        .with_for_update()
    )
    if command is None:
        raise LookupError("Command not found")

    if command.status in (DeviceCommandStatus.ACKNOWLEDGED, DeviceCommandStatus.FAILED):
        same_result = (
            (success and command.status == DeviceCommandStatus.ACKNOWLEDGED)
            or (not success and command.status == DeviceCommandStatus.FAILED and command.failure_code == failure_code)
        )
        if same_result:
            return command, False
        raise ValueError("Command has already received a different acknowledgement")

    if command.status != DeviceCommandStatus.DELIVERED:
        raise ValueError("Command is not awaiting acknowledgement")
    if _as_utc(command.expires_at) <= _as_utc(now):
        command.status = DeviceCommandStatus.EXPIRED
        command.failure_code = "COMMAND_EXPIRED"
        command.failure_detail = "Command expired before successful acknowledgement."
        db.commit()
        raise TimeoutError("Command has expired")

    command.acknowledged_at = now
    if success:
        command.status = DeviceCommandStatus.ACKNOWLEDGED
        command.failure_code = None
        command.failure_detail = None
    else:
        command.status = DeviceCommandStatus.FAILED
        command.failure_code = failure_code or "UNKNOWN"
        command.failure_detail = safe_failure_detail(command.failure_code)
    db.commit()
    db.refresh(command)
    return command, True
