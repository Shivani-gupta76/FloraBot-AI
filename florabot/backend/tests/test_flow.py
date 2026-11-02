import json
from datetime import timedelta

import pytest

from app.analysis import finish_interrupted_analyses
from app.db import SessionLocal, utcnow
from app.decision import Recommendation
from app.messages import NO_COMMAND_MESSAGE
from app.main import app
from app.models import Analysis, Command
from app.deps import get_provider
from app.vision.mock import MockProvider
from tests.conftest import DEVICE_HEADERS, image_bytes


class FakeProvider:
    name = "fake"

    def __init__(self, raw: str | None = None, error: Exception | None = None):
        self.raw, self.error = raw, error

    def analyze(self, image: bytes, mime_type: str, model=None) -> str:
        if self.error:
            raise self.error
        return self.raw


def use_provider(provider) -> None:
    app.dependency_overrides[get_provider] = lambda: provider


def analyze(client, recommendation=Recommendation.WATERING_RECOMMENDED) -> dict:
    use_provider(MockProvider(recommendation))
    response = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")})
    assert response.status_code == 202
    return client.get(f"/api/analyses/{response.json()['analysis_id']}").json()


def refresh(client, analysis: dict) -> dict:
    return client.get(f"/api/analyses/{analysis['analysis_id']}").json()


def poll(client) -> dict | None:
    response = client.post("/api/device/poll", headers=DEVICE_HEADERS)
    assert response.status_code == 200
    return response.json()["command"]


def ack(client, command_id: str, success: bool = True, led_state: str = "ON", device_id: str = "esp32-test"):
    return client.post(
        f"/api/device/commands/{command_id}/ack",
        headers=DEVICE_HEADERS,
        json={"device_id": device_id, "success": success, "led_state": led_state},
    )


def test_recommended_turns_led1_on_only_after_acknowledgement(client):
    analysis = analyze(client)
    assert analysis["status"] == "COMPLETED"
    assert analysis["recommendation"] == "WATERING_RECOMMENDED"
    assert "check that the soil is dry" in analysis["message"]
    assert analysis["hardware"]["command_status"] == "PENDING"
    assert analysis["hardware"]["message"].startswith("FloraBOT has requested activation")
    assert analysis["hardware"]["confirmed_state"] is None

    command = poll(client)
    assert (command["led"], command["requested_state"], command["device_id"]) == ("LED1", "ON", "esp32-test")
    delivered = refresh(client, analysis)["hardware"]
    assert delivered["command_status"] == "DELIVERED"
    assert delivered["confirmed_state"] is None
    assert not delivered["final"]

    assert ack(client, command["command_id"]).json()["status"] == "ACKNOWLEDGED"
    confirmed = refresh(client, analysis)["hardware"]
    assert confirmed["message"] == "ESP32 confirmed that the watering alert LED is ON."
    assert confirmed["confirmed_state"] == "ON"
    assert confirmed["final"]
    assert poll(client) is None


def test_not_recommended_requests_led1_off(client):
    analysis = analyze(client, Recommendation.WATERING_NOT_RECOMMENDED)
    assert analysis["hardware"]["message"].startswith("FloraBOT has requested deactivation")
    command = poll(client)
    assert command["requested_state"] == "OFF"
    ack(client, command["command_id"], led_state="OFF")
    assert refresh(client, analysis)["hardware"]["message"] == "ESP32 confirmed that the watering alert LED is OFF."


def test_uncertain_never_creates_a_command(client):
    analysis = analyze(client, Recommendation.UNCERTAIN)
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["hardware"] == {
        "command_status": None,
        "requested_state": None,
        "confirmed_state": None,
        "message": NO_COMMAND_MESSAGE,
        "final": True,
        "expires_at": None,
    }
    assert poll(client) is None


@pytest.mark.parametrize(
    "provider",
    [FakeProvider(error=TimeoutError("model timed out")), FakeProvider(raw='{"recommendation": "WATERING_RECOMMENDED"}')],
    ids=["ai-unavailable", "invalid-ai-json"],
)
def test_ai_problems_become_uncertain(client, provider):
    use_provider(provider)
    created = client.post("/api/analyses", files={"image": ("leaf.png", image_bytes("PNG"), "image/png")}).json()
    analysis = client.get(f"/api/analyses/{created['analysis_id']}").json()
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["uncertain_reason"]
    assert analysis["hardware"]["command_status"] is None
    assert poll(client) is None


def test_invalid_upload_is_rejected_before_analysis(client):
    response = client.post("/api/analyses", files={"image": ("leaf.jpg", b"not an image", "image/jpeg")})
    assert response.status_code == 422
    assert "could not be read" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.query(Analysis).count() == 0


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}, {"Authorization": "test-device-token-0123456789"}])
def test_device_endpoints_require_the_device_token(client, headers):
    assert client.post("/api/device/poll", headers=headers).status_code == 401
    response = client.post(
        "/api/device/commands/any/ack", headers=headers, json={"device_id": "esp32-test", "success": True, "led_state": "ON"}
    )
    assert response.status_code == 401


def test_ack_must_come_from_the_commanded_device(client):
    analyze(client)
    command = poll(client)
    assert ack(client, command["command_id"], device_id="someone-else").status_code == 403
    assert ack(client, "unknown-command").status_code == 404


def test_expired_command_is_reported_as_unconfirmed(client):
    analysis = analyze(client)
    command = poll(client)
    with SessionLocal() as db:
        db.get(Command, command["command_id"]).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    hardware = refresh(client, analysis)["hardware"]
    assert hardware["command_status"] == "EXPIRED"
    assert hardware["message"] == "The plant recommendation is ready, but the hardware action could not be confirmed."
    assert hardware["final"]
    assert poll(client) is None
    assert ack(client, command["command_id"]).status_code == 409


@pytest.mark.parametrize(("success", "led_state"), [(False, "OFF"), (True, "OFF")], ids=["device-failure", "wrong-state"])
def test_failed_or_mismatched_ack_is_not_a_confirmation(client, success, led_state):
    analysis = analyze(client)
    command = poll(client)
    assert ack(client, command["command_id"], success=success, led_state=led_state).json()["status"] == "FAILED"
    hardware = refresh(client, analysis)["hardware"]
    assert hardware["message"] == "The plant recommendation is ready, but the ESP32 could not complete the LED action."
    assert hardware["confirmed_state"] is None


def test_duplicate_ack_is_idempotent_and_conflicting_ack_is_rejected(client):
    analyze(client)
    command = poll(client)
    assert ack(client, command["command_id"]).status_code == 200
    assert ack(client, command["command_id"]).status_code == 200
    assert ack(client, command["command_id"], success=False, led_state="OFF").status_code == 409


def test_command_is_redelivered_until_acknowledged(client):
    analyze(client)
    assert poll(client)["command_id"] == poll(client)["command_id"]


def test_newer_analysis_supersedes_unconfirmed_command(client):
    first = analyze(client)
    second = analyze(client, Recommendation.WATERING_NOT_RECOMMENDED)
    assert refresh(client, first)["hardware"]["command_status"] == "SUPERSEDED"
    command = poll(client)
    assert command["requested_state"] == "OFF"
    assert ack(client, command["command_id"], led_state="OFF").status_code == 200
    assert refresh(client, second)["hardware"]["confirmed_state"] == "OFF"


def test_pending_message_warns_when_esp32_has_not_checked_in(client):
    analysis = analyze(client)
    assert "has not checked in recently" in analysis["hardware"]["message"]
    poll(client)
    assert "has not checked in recently" not in refresh(client, analysis)["hardware"]["message"]


def test_unknown_analysis_returns_404(client):
    response = client.get("/api/analyses/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "This analysis was not found. Please upload the photo again."


@pytest.mark.parametrize(("path", "text"), [("/", "FloraBOT AI"), ("/esp32.html", "FloraBOT ESP32")])
def test_pages_are_served_and_always_revalidated(client, path, text):
    response = client.get(path)
    assert response.status_code == 200
    assert text in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert client.get("/js/api.js").headers["cache-control"] == "no-cache"


def test_analysis_reports_when_it_started_and_finished(client):
    analysis = analyze(client)
    assert analysis["created_at"] <= analysis["completed_at"]


def test_forced_uncertain_hides_the_models_conflicting_verdict(client):
    reply = {
        "plant_detected": True,
        "leaves_visible": True,
        "image_quality": "POOR",
        "observations": ["The photo is blurred"],
        "recommendation": "WATERING_RECOMMENDED",
        "confidence_level": "HIGH",
        "explanation": "The plant needs water.",
        "suggested_action": "Water it now.",
    }
    use_provider(FakeProvider(raw=json.dumps(reply)))
    created = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}).json()
    analysis = client.get(f"/api/analyses/{created['analysis_id']}").json()
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["observations"] == ["The photo is blurred"]
    assert analysis["uncertain_reason"] == "The image quality is too poor to assess."
    assert (analysis["confidence_level"], analysis["explanation"], analysis["suggested_action"]) == (None, None, None)
    assert poll(client) is None


def test_restart_closes_analyses_that_never_finished(client):
    with SessionLocal() as db:
        db.add(Analysis(id="cut-off", provider="mock"))
        db.commit()
    finish_interrupted_analyses()
    analysis = client.get("/api/analyses/cut-off").json()
    assert analysis["status"] == "COMPLETED"
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["hardware"]["message"] == NO_COMMAND_MESSAGE


@pytest.mark.parametrize(
    ("changes", "expected_start"),
    [
        ({}, "I couldn't tell from this photo whether your plant needs water."),
        ({"image_quality": "POOR"}, "I could not confidently assess watering needs from this image. Please upload a clearer photograph"),
        ({"plant_detected": False}, "I could not confidently assess watering needs from this image. Please upload a clearer photograph"),
    ],
    ids=["clear-photo", "poor-photo", "no-plant"],
)
def test_uncertain_message_matches_the_cause(client, changes, expected_start):
    reply = {
        "plant_detected": True,
        "leaves_visible": True,
        "image_quality": "GOOD",
        "observations": ["Pale spots on the leaf"],
        "recommendation": "UNCERTAIN",
        "confidence_level": "MEDIUM",
        "explanation": "No clear signs of water stress.",
        "suggested_action": "Check the soil before watering.",
        **changes,
    }
    use_provider(FakeProvider(raw=json.dumps(reply)))
    created = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}).json()
    analysis = client.get(f"/api/analyses/{created['analysis_id']}").json()
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["message"].startswith(expected_start)
    assert analysis["message"].endswith("The existing LED state has not been changed.")
