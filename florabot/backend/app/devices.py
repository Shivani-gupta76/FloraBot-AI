import asyncio
import logging
from contextlib import suppress
from enum import StrEnum

from sqlalchemy.orm import Session

from app.commands import CommandClosed, CommandNotFound, acknowledge_command, last_reported_led_state, poll_command
from app.config import DeviceMode, Settings
from app.db import SessionLocal, utcnow
from app.models import Command, CommandStatus, LedState

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0


class SimulationBehaviour(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    FAILING = "FAILING"
    OFFLINE = "OFFLINE"


class SimulationUnavailable(Exception):
    pass


class RealDevice:
    """A physical ESP32 that polls the device endpoints over Wi-Fi."""

    mode = DeviceMode.REAL
    label = "ESP32"
    simulated = False

    def __init__(self, device_id: str):
        self.device_id = device_id

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class DummyDevice:
    """A simulated ESP32 inside the backend. It goes through the same command queue as the real board."""

    mode = DeviceMode.DUMMY
    label = "Simulated ESP32"
    simulated = True

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.behaviour = SimulationBehaviour.AUTO
        self.response_delay_seconds = 1.5
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            try:
                await asyncio.to_thread(self.step)
            except Exception:
                logger.exception("Simulated ESP32 poll failed")

    def step(self) -> None:
        """One poll cycle: fetch the open command and answer it the way the current behaviour says."""
        if self.behaviour is SimulationBehaviour.OFFLINE:
            return
        with SessionLocal() as db:
            now = utcnow()
            command = poll_command(db, self.device_id, now)
            if command is None or self.behaviour is SimulationBehaviour.MANUAL:
                return
            if (now - command.delivered_at).total_seconds() < self.response_delay_seconds:
                return
            self._acknowledge(db, command, success=self.behaviour is SimulationBehaviour.AUTO)

    def acknowledge_by_hand(self, command_id: str, success: bool) -> Command:
        if self.behaviour is not SimulationBehaviour.MANUAL:
            raise SimulationUnavailable("Switch the simulator to Manual to confirm commands by hand.")
        with SessionLocal() as db:
            command = db.get(Command, command_id)
            if command is None or command.device_id != self.device_id:
                raise CommandNotFound
            if command.status in (CommandStatus.ACKNOWLEDGED, CommandStatus.FAILED):
                raise CommandClosed("This command has already been answered.")
            return self._acknowledge(db, command, success)

    def _acknowledge(self, db: Session, command: Command, success: bool) -> Command:
        # A failed command leaves the LED as it was, so report the last known state.
        state = command.requested_state if success else (last_reported_led_state(db, self.device_id) or LedState.OFF)
        return acknowledge_command(db, self.device_id, command.id, success, state, utcnow(), self.label)


def build_device(settings: Settings) -> RealDevice | DummyDevice:
    if settings.device_mode is DeviceMode.REAL:
        return RealDevice(settings.device_id)
    # A separate ID keeps simulated commands and status out of the real board's history.
    return DummyDevice(f"{settings.device_id}-sim")
