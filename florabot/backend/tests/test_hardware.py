import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.decision import Recommendation
from app.deps import get_provider
from app.devices import DummyDevice, RealDevice, SimulationBehaviour
from app.main import app
from app.models import Command
from app.vision.mock import MockProvider
from tests.conftest import DEVICE_HEADERS, image_bytes


@pytest.fixture
def simulator(client) -> DummyDevice:
    """Swap in a simulated ESP32 whose poll loop is not running, so each test drives it with step()."""
    device = DummyDevice("esp32-test-sim")
    device.response_delay_seconds = 0
    app.state.device = device
    return device


def analyze(client, recommendation=Recommendation.WATERING_RECOMMENDED) -> str:
    app.dependency_overrides[get_provider] = lambda: MockProvider(recommendation)
    response = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")})
    assert response.status_code == 202
    return response.json()["analysis_id"]


def hardware_of(client, analysis_id: str) -> dict:
    return client.get(f"/api/analyses/{analysis_id}").json()["hardware"]


def test_auto_simulator_confirms_and_says_it_is_simulated(client, simulator):
    analysis_id = analyze(client)
    assert hardware_of(client, analysis_id)["expires_at"] is not None
    simulator.step()
    hardware = hardware_of(client, analysis_id)
    assert hardware["command_status"] == "ACKNOWLEDGED"
    assert hardware["message"] == "The simulated ESP32 confirmed that the watering alert LED is ON."

    status = client.get("/api/hardware").json()
    assert status["mode"] == "dummy"
    assert status["label"] == "Simulated ESP32"
    assert status["online"] is True
    assert status["led1_state"] == "ON"
    assert status["pending_command"] is None
    assert status["simulation"] == {"behaviour": "AUTO", "response_delay_seconds": 0.0}


def test_auto_simulator_waits_for_its_response_delay(client, simulator):
    simulator.response_delay_seconds = 60
    analysis_id = analyze(client)
    simulator.step()
    assert hardware_of(client, analysis_id)["command_status"] == "DELIVERED"
    assert client.get("/api/hardware").json()["pending_command"]["status"] == "DELIVERED"


def test_failing_simulator_reports_failure_and_keeps_led(client, simulator):
    first = analyze(client, Recommendation.WATERING_NOT_RECOMMENDED)
    simulator.step()
    assert client.get("/api/hardware").json()["led1_state"] == "OFF"

    simulator.behaviour = SimulationBehaviour.FAILING
    second = analyze(client)
    simulator.step()
    hardware = hardware_of(client, second)
    assert hardware["command_status"] == "FAILED"
    assert hardware["message"] == "The plant recommendation is ready, but the simulated ESP32 could not complete the LED action."
    assert hardware["confirmed_state"] is None
    assert client.get("/api/hardware").json()["led1_state"] == "OFF"
    assert hardware_of(client, first)["command_status"] == "ACKNOWLEDGED"
    assert client.get("/api/hardware/commands").json()[0]["failure"] == "Simulated ESP32 reported a failure."


def test_offline_simulator_never_polls_and_commands_expire(client, simulator):
    simulator.behaviour = SimulationBehaviour.OFFLINE
    analysis_id = analyze(client)
    simulator.step()
    hardware = hardware_of(client, analysis_id)
    assert hardware["command_status"] == "PENDING"
    assert "The simulated ESP32 has not checked in recently" in hardware["message"]
    assert client.get("/api/hardware").json()["online"] is False

    with SessionLocal() as db:
        db.get(Command, client.get("/api/hardware").json()["pending_command"]["command_id"]).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert hardware_of(client, analysis_id)["command_status"] == "EXPIRED"


def test_manual_simulator_waits_for_a_person(client, simulator):
    client.put("/api/hardware/simulation", json={"behaviour": "MANUAL", "response_delay_seconds": 0})
    analysis_id = analyze(client)
    simulator.step()
    pending = client.get("/api/hardware").json()["pending_command"]
    assert pending["status"] == "DELIVERED"
    assert hardware_of(client, analysis_id)["command_status"] == "DELIVERED"

    response = client.post(f"/api/hardware/simulation/commands/{pending['command_id']}/ack", json={"success": True})
    assert response.status_code == 200
    assert response.json()["status"] == "ACKNOWLEDGED"
    assert response.json()["acknowledged_state"] == "ON"
    assert hardware_of(client, analysis_id)["confirmed_state"] == "ON"

    for success in (True, False):
        again = client.post(f"/api/hardware/simulation/commands/{pending['command_id']}/ack", json={"success": success})
        assert again.status_code == 409
        assert again.json()["detail"] == "This command has already been answered."


def test_manual_failure_and_closed_commands(client, simulator):
    simulator.behaviour = SimulationBehaviour.MANUAL
    first = analyze(client)
    simulator.step()
    first_command = client.get("/api/hardware").json()["pending_command"]["command_id"]
    analyze(client, Recommendation.WATERING_NOT_RECOMMENDED)
    simulator.step()
    superseded = client.post(f"/api/hardware/simulation/commands/{first_command}/ack", json={"success": True})
    assert superseded.status_code == 409
    assert superseded.json()["detail"] == "A newer command replaced this one."
    assert hardware_of(client, first)["command_status"] == "SUPERSEDED"

    second_command = client.get("/api/hardware").json()["pending_command"]["command_id"]
    failed = client.post(f"/api/hardware/simulation/commands/{second_command}/ack", json={"success": False})
    assert failed.json()["status"] == "FAILED"
    assert client.post("/api/hardware/simulation/commands/nope/ack", json={"success": True}).status_code == 404


def test_manual_ack_needs_manual_behaviour(client, simulator):
    analyze(client)
    simulator.response_delay_seconds = 60
    simulator.step()
    command_id = client.get("/api/hardware").json()["pending_command"]["command_id"]
    response = client.post(f"/api/hardware/simulation/commands/{command_id}/ack", json={"success": True})
    assert response.status_code == 409
    assert response.json()["detail"] == "Switch the simulator to Manual to confirm commands by hand."


def test_simulation_settings_are_validated(client, simulator):
    response = client.put("/api/hardware/simulation", json={"behaviour": "FAILING", "response_delay_seconds": 2.5})
    assert response.json()["simulation"] == {"behaviour": "FAILING", "response_delay_seconds": 2.5}
    assert client.put("/api/hardware/simulation", json={"behaviour": "SLEEPY", "response_delay_seconds": 1}).status_code == 422
    assert client.put("/api/hardware/simulation", json={"behaviour": "AUTO", "response_delay_seconds": 21}).status_code == 422


def test_device_endpoints_are_closed_while_simulating(client, simulator):
    response = client.post("/api/device/poll", headers=DEVICE_HEADERS)
    assert response.status_code == 409
    assert "FLORABOT_DEVICE_MODE=dummy" in response.json()["detail"]


def test_real_mode_has_no_simulator(client):
    assert isinstance(app.state.device, RealDevice)
    status = client.get("/api/hardware").json()
    assert (status["mode"], status["label"], status["simulation"], status["led1_state"]) == ("real", "ESP32", None, None)
    assert status["online"] is False
    put = client.put("/api/hardware/simulation", json={"behaviour": "AUTO", "response_delay_seconds": 1})
    assert put.status_code == 409
    assert client.post("/api/hardware/simulation/commands/x/ack", json={"success": True}).status_code == 409


def test_command_log_lists_newest_first(client):
    for recommendation in (Recommendation.WATERING_RECOMMENDED, Recommendation.WATERING_NOT_RECOMMENDED):
        analyze(client, recommendation)
    log = client.get("/api/hardware/commands?limit=5").json()
    assert [entry["requested_state"] for entry in log] == ["OFF", "ON"]
    assert [entry["status"] for entry in log] == ["PENDING", "SUPERSEDED"]
    assert client.get("/api/hardware/commands?limit=0").status_code == 422


def test_dummy_mode_starts_a_working_simulator(fresh_db, monkeypatch):
    monkeypatch.setenv("FLORABOT_DEVICE_MODE", "dummy")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            assert isinstance(app.state.device, DummyDevice)
            client.put("/api/hardware/simulation", json={"behaviour": "AUTO", "response_delay_seconds": 0})
            analysis_id = analyze(client)
            deadline = time.monotonic() + 10
            while hardware_of(client, analysis_id)["command_status"] != "ACKNOWLEDGED" and time.monotonic() < deadline:
                time.sleep(0.2)
            assert hardware_of(client, analysis_id)["confirmed_state"] == "ON"
        assert app.state.device._task is None
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_simulator_history_never_shows_up_as_the_real_board(client, simulator):
    analyze(client)
    simulator.step()
    assert client.get("/api/hardware").json()["led1_state"] == "ON"

    app.state.device = RealDevice("esp32-test")
    status = client.get("/api/hardware").json()
    assert (status["device_id"], status["online"], status["led1_state"], status["pending_command"]) == ("esp32-test", False, None, None)
    assert client.get("/api/hardware/commands").json() == []

    analysis_id = analyze(client)
    command = client.post("/api/device/poll", headers=DEVICE_HEADERS).json()["command"]
    assert command["device_id"] == "esp32-test"
    assert hardware_of(client, analysis_id)["message"].startswith("FloraBOT has requested activation")


def test_build_device_gives_the_simulator_its_own_id():
    from app.config import Settings
    from app.devices import build_device

    assert build_device(Settings(device_mode="dummy", device_id="board")).device_id == "board-sim"
    assert build_device(Settings(device_mode="real", device_id="board", device_token="x" * 16)).device_id == "board"
