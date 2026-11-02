from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.commands import (
    CommandClosed,
    CommandNotFound,
    device_online,
    expire_stale_commands,
    last_reported_led_state,
    open_command,
    recent_commands,
)
from app.db import get_db, utcnow
from app.deps import get_device
from app.devices import DummyDevice, RealDevice, SimulationUnavailable
from app.models import Command, Device
from app.schemas import DeviceCommandView, HardwareStatusOut, ManualAckIn, SimulationIn, SimulationOut

router = APIRouter(prefix="/api/hardware")


def command_view(command: Command) -> DeviceCommandView:
    return DeviceCommandView(
        command_id=command.id,
        analysis_id=command.analysis_id,
        led=command.led,
        requested_state=command.requested_state,
        status=command.status,
        created_at=command.created_at,
        expires_at=command.expires_at,
        delivered_at=command.delivered_at,
        acknowledged_at=command.acknowledged_at,
        acknowledged_state=command.acknowledged_state,
        failure=command.failure,
    )


def hardware_status(db: Session, device: RealDevice | DummyDevice, now: datetime) -> HardwareStatusOut:
    expire_stale_commands(db, now)
    db.commit()
    record = db.get(Device, device.device_id)
    pending = open_command(db, device.device_id)
    simulation = None
    if isinstance(device, DummyDevice):
        simulation = SimulationOut(behaviour=device.behaviour, response_delay_seconds=device.response_delay_seconds)
    return HardwareStatusOut(
        mode=device.mode,
        device_id=device.device_id,
        label=device.label,
        online=device_online(db, device.device_id, now),
        last_seen_at=record.last_seen_at if record else None,
        led1_state=last_reported_led_state(db, device.device_id),
        simulation=simulation,
        pending_command=command_view(pending) if pending else None,
    )


def simulator(device: RealDevice | DummyDevice = Depends(get_device)) -> DummyDevice:
    if not isinstance(device, DummyDevice):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The ESP32 simulator is only available when FLORABOT_DEVICE_MODE=dummy."
        )
    return device


@router.get("")
def get_hardware(db: Session = Depends(get_db), device: RealDevice | DummyDevice = Depends(get_device)) -> HardwareStatusOut:
    return hardware_status(db, device, utcnow())


@router.get("/commands")
def list_commands(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    device: RealDevice | DummyDevice = Depends(get_device),
) -> list[DeviceCommandView]:
    expire_stale_commands(db, utcnow())
    db.commit()
    return [command_view(command) for command in recent_commands(db, device.device_id, limit)]


@router.put("/simulation")
def update_simulation(
    settings: SimulationIn, db: Session = Depends(get_db), device: DummyDevice = Depends(simulator)
) -> HardwareStatusOut:
    device.behaviour = settings.behaviour
    device.response_delay_seconds = settings.response_delay_seconds
    return hardware_status(db, device, utcnow())


@router.post("/simulation/commands/{command_id}/ack")
def acknowledge_by_hand(command_id: str, ack: ManualAckIn, device: DummyDevice = Depends(simulator)) -> DeviceCommandView:
    try:
        command = device.acknowledge_by_hand(command_id, ack.success)
    except SimulationUnavailable as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error))
    except CommandNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This LED command was not found.")
    except CommandClosed as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error))
    return command_view(command)
