import logging

from pydantic import ValidationError

from app.db import SessionLocal, utcnow
from app.decision import HealthReview
from app.disease import DiseaseClassifier, DiseasePrediction, readable
from app.models import HealthCheck, HealthStatus
from app.vision.base import VisionProvider

logger = logging.getLogger(__name__)


def leaf_model_summary(prediction: DiseasePrediction, labels: list[str]) -> str:
    """What the reviewer needs to know about the leaf model and what it said about this photo."""
    known = ", ".join(" · ".join(readable(label)) for label in labels)
    scores = ", ".join(f"{' · '.join(readable(label))} {score:.0%}" for label, score in prediction.scores)
    return f"Labels it knows: {known}.\nIts top scores for this photo: {scores}."


def review_health(
    provider: VisionProvider, image: bytes, mime_type: str, leaf_model: str, model: str | None = None
) -> HealthReview | None:
    try:
        raw = provider.review_health(image, mime_type, leaf_model, model=model)
    except Exception:
        logger.exception("Vision provider %s could not review plant health", provider.name)
        return None
    try:
        return HealthReview.model_validate_json(raw)
    except ValidationError:
        logger.warning("Vision provider %s returned an unusable health review", provider.name)
        return None


def run_health_check(
    analysis_id: str,
    image: bytes,
    mime_type: str,
    classifier: DiseaseClassifier,
    provider: VisionProvider,
    model: str | None = None,
) -> None:
    """Saves the local leaf model's result first, then the AI provider's closer look that uses it as context."""
    try:
        prediction = classifier.classify(image)
    except Exception:
        logger.exception("Leaf model %s failed", classifier.name)
        prediction = None
    with SessionLocal() as db:
        check = db.get(HealthCheck, analysis_id)
        if prediction is not None:
            check.leaf_label = prediction.label
            check.leaf_confidence = prediction.confidence
            check.leaf_alternatives = prediction.alternatives
        check.status = HealthStatus.REVIEWING
        db.commit()

    leaf_model = leaf_model_summary(prediction, classifier.labels) if prediction else "The leaf model could not check this photo."
    review = review_health(provider, image, mime_type, leaf_model, model)
    with SessionLocal() as db:
        check = db.get(HealthCheck, analysis_id)
        check.review = review.model_dump(mode="json") if review else None
        check.status = HealthStatus.DONE if review else HealthStatus.REVIEW_UNAVAILABLE
        check.completed_at = utcnow()
        db.commit()
