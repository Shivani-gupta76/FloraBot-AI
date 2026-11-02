from google import genai
from google.genai import types

from app.decision import HealthReview, VisionResult
from app.vision.base import ModelChoice
from app.vision.prompt import ANALYSIS_PROMPT, CARE_PROMPT, HEALTH_REVIEW_PROMPT

# Timeouts come from live tests on the free tier: Flash-Lite answers in seconds, Flash sometimes takes minutes.
GEMINI_MODELS = [
    ModelChoice("gemini-flash-lite-latest", "Gemini Flash-Lite", "Fastest. Usually answers in a few seconds.", 30),
    ModelChoice("gemini-flash-latest", "Gemini Flash", "More thorough, but can take a minute or more.", 150),
    ModelChoice("gemini-pro-latest", "Gemini Pro", "Most capable. Needs a paid Gemini plan.", 150),
]


def gemini_client(api_key: str, timeout_seconds: int) -> genai.Client:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_seconds * 1000, retry_options=types.HttpRetryOptions(attempts=3)),
    )


class GeminiProvider:
    """Google Gemini through the official google-genai SDK."""

    name = "gemini"
    models = GEMINI_MODELS

    def __init__(self, client: genai.Client, model: str, review_model: str | None = None, review_timeout_seconds: int = 90):
        self._client = client
        self.default_model = model
        self.default_review_model = review_model or model
        self._review_timeout_seconds = review_timeout_seconds

    def _timeout(self, model: str, fallback_seconds: int | None) -> types.HttpOptions | None:
        seconds = next((choice.timeout_seconds for choice in self.models if choice.id == model), fallback_seconds)
        return types.HttpOptions(timeout=seconds * 1000) if seconds else None

    def analyze(self, image: bytes, mime_type: str, model: str | None = None) -> str:
        chosen = model or self.default_model
        response = self._client.models.generate_content(
            model=chosen,
            contents=[types.Part.from_bytes(data=image, mime_type=mime_type), ANALYSIS_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=VisionResult.model_json_schema(),
                # Zero temperature, so the same photo gets the same watering decision.
                temperature=0,
                http_options=self._timeout(chosen, None),
            ),
        )
        return response.text or ""

    def answer_question(self, question: str, model: str | None = None) -> str:
        chosen = model or self.default_model
        response = self._client.models.generate_content(
            model=chosen,
            contents=question,
            config=types.GenerateContentConfig(system_instruction=CARE_PROMPT, temperature=0.4, http_options=self._timeout(chosen, None)),
        )
        return response.text or ""

    def review_health(self, image: bytes, mime_type: str, leaf_model: str, model: str | None = None) -> str:
        chosen = model or self.default_review_model
        response = self._client.models.generate_content(
            model=chosen,
            contents=[types.Part.from_bytes(data=image, mime_type=mime_type), HEALTH_REVIEW_PROMPT.replace("{leaf_model}", leaf_model)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=HealthReview.model_json_schema(),
                temperature=0,
                http_options=self._timeout(chosen, self._review_timeout_seconds),
            ),
        )
        return response.text or ""
