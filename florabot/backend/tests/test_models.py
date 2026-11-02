import json

import httpx
from google import genai
from google.genai import types

from app.decision import Recommendation
from app.deps import get_provider
from app.main import app
from app.vision.base import ModelChoice
from app.vision.gemini import GEMINI_MODELS, GeminiProvider
from app.vision.mock import MOCK_HEALTH_REVIEW, MockProvider, _RESULTS
from tests.conftest import image_bytes

CHOICES = [ModelChoice("fast", "Fast", "Quick answers.", 30), ModelChoice("deep", "Deep", "Slower, more thorough.", 150)]


class ChoosyProvider:
    """Offers two models and records which one each call used."""

    name = "choosy"
    models = CHOICES
    default_model = "fast"
    default_review_model = "fast"

    def __init__(self):
        self.calls = []

    def analyze(self, image, mime_type, model=None):
        self.calls.append(("analyze", model))
        return _RESULTS[Recommendation.WATERING_NOT_RECOMMENDED].model_dump_json()

    def answer_question(self, question, model=None):
        self.calls.append(("answer", model))
        return "Water when the top 2 cm are dry."

    def review_health(self, image, mime_type, leaf_model, model=None):
        self.calls.append(("review", model))
        return MOCK_HEALTH_REVIEW


def upload(client, **fields):
    return client.post("/api/analyses", files={"image": ("leaf.jpg", image_bytes(), "image/jpeg")}, data=fields)


def test_mock_offers_no_model_choice(client):
    assert client.get("/api/ai/models").json() == {"choices": [], "default_model": None, "default_review_model": None}


def test_model_options_list_the_providers_choices(client):
    app.dependency_overrides[get_provider] = lambda: ChoosyProvider()
    options = client.get("/api/ai/models").json()
    assert [choice["id"] for choice in options["choices"]] == ["fast", "deep"]
    assert options["choices"][1] == {"id": "deep", "label": "Deep", "description": "Slower, more thorough."}
    assert (options["default_model"], options["default_review_model"]) == ("fast", "fast")


def test_chosen_models_reach_the_watering_check_and_the_review(client):
    provider = ChoosyProvider()
    app.dependency_overrides[get_provider] = lambda: provider
    assert upload(client, model="fast", review_model="deep").status_code == 202
    assert sorted(provider.calls) == [("analyze", "fast"), ("review", "deep")]


def test_no_choice_means_the_providers_defaults(client):
    provider = ChoosyProvider()
    app.dependency_overrides[get_provider] = lambda: provider
    upload(client)
    assert sorted(provider.calls) == [("analyze", None), ("review", None)]


def test_unknown_models_are_rejected(client):
    app.dependency_overrides[get_provider] = lambda: ChoosyProvider()
    for fields in ({"model": "gpt-5"}, {"review_model": "gemini-ultra"}):
        response = upload(client, **fields)
        assert response.status_code == 422
        assert response.json()["detail"] == "This AI model isn't available."
    response = client.post("/api/care/answers", json={"question": "When to water?", "model": "nope"})
    assert response.status_code == 422


def test_mock_rejects_any_model_choice(client):
    assert upload(client, model="gemini-flash-latest").status_code == 422


def test_care_answer_uses_the_chosen_model(client):
    provider = ChoosyProvider()
    app.dependency_overrides[get_provider] = lambda: provider
    assert client.post("/api/care/answers", json={"question": "When to water?", "model": "deep"}).status_code == 200
    assert provider.calls == [("answer", "deep")]


def test_gemini_calls_the_chosen_model_or_its_default():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path.rsplit("/", 1)[-1])
        text = _RESULTS[Recommendation.WATERING_RECOMMENDED].model_dump_json()
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]})

    client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=httpx.Client(transport=httpx.MockTransport(handler))))
    provider = GeminiProvider(client, "gemini-flash-lite-latest", "gemini-flash-lite-latest")
    provider.analyze(image_bytes(), "image/jpeg")
    provider.analyze(image_bytes(), "image/jpeg", model="gemini-flash-latest")
    provider.review_health(image_bytes(), "image/jpeg", "Its top scores for this photo: none.", model="gemini-pro-latest")
    provider.answer_question("When to water?", model="gemini-flash-latest")
    assert paths == [
        "gemini-flash-lite-latest:generateContent",
        "gemini-flash-latest:generateContent",
        "gemini-pro-latest:generateContent",
        "gemini-flash-latest:generateContent",
    ]


def test_gemini_offers_the_models_checked_live():
    assert [choice.id for choice in GEMINI_MODELS] == ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest"]
    assert all(choice.timeout_seconds >= 30 for choice in GEMINI_MODELS)
