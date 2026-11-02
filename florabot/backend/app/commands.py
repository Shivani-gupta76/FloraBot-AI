from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OPEN_COMMAND_STATUSES, Command, CommandStatus, Device, LedState


class CommandNotFound(Exception):
    pass


class CommandClosed(Exception):
    pass


def create_led1_command(db: Session, analysis_id: str, device_id: str, state: LedState, now: datetime) -> Command:
    """Queue an LED1 command, replacing any older command the device has not confirmed yet."""
    db.execute(
        update(Command)
        .where(Command.device_id == device_id, Command.status.in_(OPEN_COMMAND_STATUSES))
        .values(status=CommandStatus.SUPERSEDED)
    )
    command = Command(
        analysis_id=analysis_id,
        device_id=device_id,
        requested_state=state,
        created_at=now,
        expires_at=now + timedelta(seconds=get_settings().command_ttl_seconds),
    )
    db.add(command)
    return command


def expire_stale_commands(db: Session, now: datetime) -> None:
    db.execute(
        update(Command)
        .where(Command.status.in_(OPEN_COMMAND_STATUSES), Command.expires_at <= now)
        .values(status=CommandStatus.EXPIRED, failure="No acknowledgement before the command expired.")
    )


def device_online(db: Session, device_id: str, now: datetime) -> bool:
    device = db.get(Device, device_id)
    timeout = timedelta(seconds=get_settings().device_offline_seconds)
    return device is not None and now - device.last_seen_at <= timeout


def open_command(db: Session, device_id: str) -> Command | None:
    return db.scalar(
        select(Command)
        .where(Command.device_id == device_id, Command.status.in_(OPEN_COMMAND_STATUSES))
        .order_by(Command.created_at.desc())
        .limit(1)
    )


def recent_commands(db: Session, device_id: str, limit: int) -> list[Command]:
    return list(
        db.scalars(select(Command).where(Command.device_id == device_id).order_by(Command.created_at.desc()).limit(limit))
    )


def last_reported_led_state(db: Session, device_id: str) -> LedState | None:
    """LED1 state from the device's most recent acknowledgement, successful or not."""
    return db.scalar(
        select(Command.acknowledged_state)
        .where(Command.device_id == device_id, Command.acknowledged_at.is_not(None))
        .order_by(Command.acknowledged_at.desc())
        .limit(1)
    )


def poll_command(db: Session, device_id: str, now: datetime) -> Command | None:
    """Return the device's open command. It is re-sent until acknowledged; LED states are idempotent."""
    expire_stale_commands(db, now)
    db.merge(Device(id=device_id, last_seen_at=now))
    command = open_command(db, device_id)
    if command is not None and command.status is CommandStatus.PENDING:
        command.status = CommandStatus.DELIVERED
        command.delivered_at = now
    db.commit()
    return command


def acknowledge_command(
    db: Session,
    device_id: str,
    command_id: str,
    success: bool,
    led_state: LedState,
    now: datetime,
    device_label: str = "ESP32",
) -> Command:
    command = db.get(Command, command_id)
    if command is None or command.device_id != device_id:
        raise CommandNotFound

    if command.status in OPEN_COMMAND_STATUSES and command.expires_at <= now:
        expire_stale_commands(db, now)
        db.commit()
        db.refresh(command)

    if command.status in (CommandStatus.ACKNOWLEDGED, CommandStatus.FAILED):
        if success == (command.status is CommandStatus.ACKNOWLEDGED) and led_state == command.acknowledged_state:
            return command
        raise CommandClosed("This command already has a different acknowledgement.")
    if command.status is CommandStatus.EXPIRED:
        raise CommandClosed("This command has expired.")
    if command.status is CommandStatus.SUPERSEDED:
        raise CommandClosed("A newer command replaced this one.")

    command.acknowledged_at = now
    command.acknowledged_state = led_state
    if success and led_state == command.requested_state:
        command.status = CommandStatus.ACKNOWLEDGED
    else:
        command.status = CommandStatus.FAILED
        command.failure = f"{device_label} reported a failure." if not success else f"{device_label} reported LED1 {led_state}."
    db.commit()
    return command
