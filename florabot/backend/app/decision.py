from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError


class Recommendation(StrEnum):
    WATERING_RECOMMENDED = "WATERING_RECOMMENDED"
    WATERING_NOT_RECOMMENDED = "WATERING_NOT_RECOMMENDED"
    UNCERTAIN = "UNCERTAIN"


class ImageQuality(StrEnum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class VisionResult(BaseModel):
    """The JSON every vision provider must return."""

    model_config = ConfigDict(strict=True)

    plant_detected: bool
    leaves_visible: bool
    image_quality: ImageQuality
    observations: list[str]
    recommendation: Recommendation
    confidence_level: Confidence
    explanation: str
    suggested_action: str


class HealthFinding(StrEnum):
    HEALTHY = "HEALTHY"
    DISEASE = "DISEASE"
    PEST = "PEST"
    NUTRIENT_OR_ENVIRONMENT = "NUTRIENT_OR_ENVIRONMENT"
    UNCLEAR = "UNCLEAR"


class HealthReview(BaseModel):
    """The JSON a provider returns when it takes a closer look at plant health."""

    model_config = ConfigDict(strict=True)

    plant: str
    finding: HealthFinding
    problem: str
    possible_causes: list[str]
    confidence_level: Confidence
    agrees_with_leaf_model: bool
    observations: list[str]
    advice: str


@dataclass(frozen=True)
class Decision:
    recommendation: Recommendation
    result: VisionResult | None
    uncertain_reason: str | None = None


def uncertain(reason: str, result: VisionResult | None = None) -> Decision:
    return Decision(Recommendation.UNCERTAIN, result, reason)


def decide(raw_response: str) -> Decision:
    """Validate a provider's raw JSON and apply the rules that force UNCERTAIN."""
    try:
        result = VisionResult.model_validate_json(raw_response)
    except ValidationError:
        return uncertain("The analysis didn't return a usable result.")

    if not result.plant_detected:
        return uncertain("No plant was detected in the image.", result)
    if result.image_quality is ImageQuality.POOR:
        return uncertain("The image quality is too poor to assess.", result)
    if not result.leaves_visible:
        return uncertain("The leaves are not clearly visible.", result)
    return Decision(result.recommendation, result)
