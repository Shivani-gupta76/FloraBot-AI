from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelChoice:
    """A model the user may pick in the chat."""

    id: str
    label: str
    description: str
    timeout_seconds: int


class VisionProvider(Protocol):
    """Adapter for an AI model.

    `analyze` returns the model's raw JSON text for a plant photo. Parsing and safety checks
    happen in app.decision, so a provider never decides what the LED does.
    `answer_question` returns a short plain-text answer to a plant-care question.
    `review_health` returns raw JSON (app.decision.HealthReview) judging the photo, with the leaf model's result as a hint.
    Each method takes an optional `model`, one of `models`, chosen by the user; None means the provider's default.
    """

    name: str
    models: list[ModelChoice]
    default_model: str | None
    default_review_model: str | None

    def analyze(self, image: bytes, mime_type: str, model: str | None = None) -> str: ...

    def answer_question(self, question: str, model: str | None = None) -> str: ...

    def review_health(self, image: bytes, mime_type: str, leaf_model: str, model: str | None = None) -> str: ...
