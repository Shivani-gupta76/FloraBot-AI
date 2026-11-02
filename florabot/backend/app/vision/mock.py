import time

from app.decision import Confidence, ImageQuality, Recommendation, VisionResult

_RESULTS = {
    Recommendation.WATERING_RECOMMENDED: VisionResult(
        plant_detected=True,
        leaves_visible=True,
        image_quality=ImageQuality.GOOD,
        observations=["The leaves appear visibly drooped", "Some leaf edges appear dry"],
        recommendation=Recommendation.WATERING_RECOMMENDED,
        confidence_level=Confidence.MEDIUM,
        explanation="Mock result: the plant shows visible symptoms commonly associated with water stress.",
        suggested_action="Check whether the soil is dry before watering.",
    ),
    Recommendation.WATERING_NOT_RECOMMENDED: VisionResult(
        plant_detected=True,
        leaves_visible=True,
        image_quality=ImageQuality.GOOD,
        observations=["The leaves appear upright and firm", "The leaf colour looks even"],
        recommendation=Recommendation.WATERING_NOT_RECOMMENDED,
        confidence_level=Confidence.MEDIUM,
        explanation="Mock result: the plant shows no clear visible signs of water stress.",
        suggested_action="Keep monitoring the plant and check the soil before any watering.",
    ),
    Recommendation.UNCERTAIN: VisionResult(
        plant_detected=True,
        leaves_visible=True,
        image_quality=ImageQuality.ACCEPTABLE,
        observations=["Some leaves look slightly curled while others look healthy"],
        recommendation=Recommendation.UNCERTAIN,
        confidence_level=Confidence.LOW,
        explanation="Mock result: the visible evidence is mixed.",
        suggested_action="Check the soil moisture by hand.",
    ),
}


MOCK_CARE_ANSWER = """\
Mock answer: FloraBOT is running without a real AI model, so this is general advice.

- Check the top 2–3 cm of soil with your finger before watering
- Water thoroughly, then let the extra water drain away
- Most houseplants prefer bright, indirect light

Set FLORABOT_VISION_PROVIDER=gemini to get real answers."""

MOCK_HEALTH_REVIEW = """{"plant": "Tomato", "finding": "HEALTHY", "problem": "", "possible_causes": [], "confidence_level": "MEDIUM",
"agrees_with_leaf_model": true, "observations": ["Mock review: the leaves look evenly green and firm."],
"advice": "Keep checking the leaves once a week."}"""


class MockProvider:
    """Returns fixed results so the full workflow can run without a real model."""

    name = "mock"
    models = []
    default_model = None
    default_review_model = None

    def __init__(self, recommendation: Recommendation, delay_seconds: float = 0.0):
        self._response = _RESULTS[recommendation].model_dump_json()
        self._delay_seconds = delay_seconds

    def analyze(self, image: bytes, mime_type: str, model: str | None = None) -> str:
        time.sleep(self._delay_seconds)
        return self._response

    def answer_question(self, question: str, model: str | None = None) -> str:
        time.sleep(self._delay_seconds)
        return MOCK_CARE_ANSWER

    def review_health(self, image: bytes, mime_type: str, leaf_model: str, model: str | None = None) -> str:
        time.sleep(self._delay_seconds)
        return MOCK_HEALTH_REVIEW
