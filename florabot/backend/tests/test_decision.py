import json

import pytest

from app.decision import Recommendation, decide

VALID = {
    "plant_detected": True,
    "leaves_visible": True,
    "image_quality": "GOOD",
    "observations": ["The leaves appear visibly drooped"],
    "recommendation": "WATERING_RECOMMENDED",
    "confidence_level": "MEDIUM",
    "explanation": "Visible symptoms of water stress.",
    "suggested_action": "Check whether the soil is dry before watering.",
}


def response(**changes) -> str:
    return json.dumps({**VALID, **changes})


def test_valid_response_keeps_ai_recommendation():
    decision = decide(response(recommendation="WATERING_NOT_RECOMMENDED"))
    assert decision.recommendation is Recommendation.WATERING_NOT_RECOMMENDED
    assert decision.uncertain_reason is None


@pytest.mark.parametrize(
    "raw",
    [
        response(plant_detected=False),
        response(image_quality="POOR"),
        response(leaves_visible=False),
        response(recommendation="WATER_NOW"),
        response(confidence_level=0.9),
        response(plant_detected="yes"),
        json.dumps({key: value for key, value in VALID.items() if key != "recommendation"}),
        "this is not json",
        "",
    ],
)
def test_unsafe_responses_force_uncertain(raw):
    decision = decide(raw)
    assert decision.recommendation is Recommendation.UNCERTAIN
    assert decision.uncertain_reason
