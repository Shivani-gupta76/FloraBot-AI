import base64
import json

import httpx
import pytest
from google import genai
from google.genai import types

from app.config import Settings
from app.decision import Recommendation, decide
from app.main import app
from app.deps import get_provider
from app.vision import build_provider
from app.vision.gemini import GeminiProvider
from app.decision import HealthReview
from app.vision.prompt import ANALYSIS_PROMPT, CARE_PROMPT
from tests.conftest import image_bytes

MODEL_REPLY = {
    "plant_detected": True,
    "leaves_visible": True,
    "image_quality": "GOOD",
    "observations": ["The leaves are drooping"],
    "recommendation": "WATERING_RECOMMENDED",
    "confidence_level": "MEDIUM",
    "explanation": "Drooping leaves are commonly linked to water stress.",
    "suggested_action": "Check that the soil is dry before watering.",
}


def gemini_with_fake_network(handler) -> GeminiProvider:
    """A provider that runs the real google-genai SDK against a fake HTTP server."""
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=http))
    return GeminiProvider(client, "gemini-test-model")


def reply_with(text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}
        )

    return handler


def test_sends_image_prompt_and_schema_to_gemini():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return reply_with(json.dumps(MODEL_REPLY))(request)

    photo = image_bytes("PNG")
    raw = gemini_with_fake_network(handler).analyze(photo, "image/png")

    assert decide(raw).recommendation is Recommendation.WATERING_RECOMMENDED
    request = requests[0]
    assert request.url.path.endswith("/models/gemini-test-model:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    image_part, prompt_part = body["contents"][0]["parts"]
    assert image_part["inlineData"]["data"] == base64.b64encode(photo).decode()
    assert "image/png" in image_part["inlineData"].values()
    assert prompt_part["text"] == ANALYSIS_PROMPT
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert set(config["responseJsonSchema"]["required"]) == set(MODEL_REPLY)


def test_gemini_error_becomes_uncertain_in_the_chat(client):
    provider = gemini_with_fake_network(lambda request: httpx.Response(429, json={"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}))
    app.dependency_overrides[get_provider] = lambda: provider
    created = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}).json()
    analysis = client.get(f"/api/analyses/{created['analysis_id']}").json()
    assert analysis["provider"] == "gemini"
    assert analysis["recommendation"] == "UNCERTAIN"
    assert analysis["uncertain_reason"] == "The analysis service is unavailable right now."
    assert analysis["message"].startswith("I couldn't analyze this photo right now.")
    assert analysis["hardware"]["command_status"] is None


def test_gemini_result_drives_the_led_command(client):
    app.dependency_overrides[get_provider] = lambda: gemini_with_fake_network(reply_with(json.dumps(MODEL_REPLY)))
    created = client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}).json()
    analysis = client.get(f"/api/analyses/{created['analysis_id']}").json()
    assert analysis["recommendation"] == "WATERING_RECOMMENDED"
    assert analysis["observations"] == ["The leaves are drooping"]
    assert analysis["hardware"]["requested_state"] == "ON"


def test_build_provider_requires_a_gemini_key():
    with pytest.raises(ValueError, match="FLORABOT_GEMINI_API_KEY"):
        build_provider(Settings(vision_provider="gemini", gemini_api_key=None))
    provider = build_provider(Settings(vision_provider="gemini", gemini_api_key="any-key", gemini_model="m"))
    assert isinstance(provider, GeminiProvider)
    with pytest.raises(ValueError, match="Unknown vision provider"):
        build_provider(Settings(vision_provider="nope"))


def test_care_question_goes_to_gemini_with_the_care_rules(client):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return reply_with("Check the top 2-3 cm of soil first.\n\n- Water if it feels dry")(request)

    app.dependency_overrides[get_provider] = lambda: gemini_with_fake_network(handler)
    response = client.post("/api/care/answers", json={"question": "How often should I water basil?"})
    assert response.json() == {"answer": "Check the top 2-3 cm of soil first.\n\n- Water if it feels dry", "provider": "gemini"}
    body = json.loads(requests[0].content)
    assert body["contents"][0]["parts"][0]["text"] == "How often should I water basil?"
    assert body["systemInstruction"]["parts"][0]["text"] == CARE_PROMPT


def test_health_review_uses_its_own_model_and_the_leaf_model_context():
    requests = []
    review = {
        "plant": "Tomato", "finding": "PEST", "problem": "Whiteflies", "possible_causes": [], "confidence_level": "MEDIUM",
        "agrees_with_leaf_model": False, "observations": ["Small white insects."], "advice": "Check under the leaves.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return reply_with(json.dumps(review))(request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=http))
    provider = GeminiProvider(client, "fast-model", "pro-model")
    raw = provider.review_health(image_bytes(), "image/jpeg", "Its top scores for this photo: Tomato · Healthy 46%.")

    assert HealthReview.model_validate_json(raw).problem == "Whiteflies"
    assert requests[0].url.path.endswith("/models/pro-model:generateContent")
    body = json.loads(requests[0].content)
    prompt = body["contents"][0]["parts"][1]["text"]
    assert "Its top scores for this photo: Tomato · Healthy 46%." in prompt and "{leaf_model}" not in prompt
    assert set(body["generationConfig"]["responseJsonSchema"]["required"]) == set(review)
