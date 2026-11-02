import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.commands import CommandClosed, CommandNotFound, acknowledge_command, poll_command
from app.config import DeviceMode, get_settings
from app.db import get_db, utcnow
from app.schemas import AckIn, AckOut, DeviceCommandOut, PollOut

router = APIRouter(prefix="/api/device")


def authenticated_device(request: Request, authorization: str | None = Header(default=None)) -> str:
    if request.app.state.device.mode is not DeviceMode.REAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "Device endpoints are disabled while FLORABOT_DEVICE_MODE=dummy.")
    settings = get_settings()
    expected = f"Bearer {settings.device_token.get_secret_value()}"
    if authorization is None or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device credentials")
    return settings.device_id


@router.post("/poll")
def poll(device_id: str = Depends(authenticated_device), db: Session = Depends(get_db)) -> PollOut:
    command = poll_command(db, device_id, utcnow())
    if command is None:
        return PollOut(command=None)
    return PollOut(
        command=DeviceCommandOut(
            command_id=command.id,
            device_id=command.device_id,
            led=command.led,
            requested_state=command.requested_state,
            created_at=command.created_at,
            expires_at=command.expires_at,
        )
    )


@router.post("/commands/{command_id}/ack")
def acknowledge(
    command_id: str,
    ack: AckIn,
    device_id: str = Depends(authenticated_device),
    db: Session = Depends(get_db),
) -> AckOut:
    if ack.device_id != device_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device ID does not match the credentials")
    try:
        command = acknowledge_command(db, device_id, command_id, ack.success, ack.led_state, utcnow())
    except CommandNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This LED command was not found.")
    except CommandClosed as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error))
    return AckOut(command_id=command.id, status=command.status)
