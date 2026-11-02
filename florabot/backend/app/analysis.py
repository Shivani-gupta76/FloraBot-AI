import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import update

from app.commands import create_led1_command
from app.db import SessionLocal, utcnow
from app.decision import Decision, Recommendation, decide, uncertain
from app.disease import DiseaseClassifier
from app.health import run_health_check
from app.models import Analysis, AnalysisStatus, HealthCheck, HealthStatus, LedState
from app.vision.base import VisionProvider

logger = logging.getLogger(__name__)

_LED_STATES = {
    Recommendation.WATERING_RECOMMENDED: LedState.ON,
    Recommendation.WATERING_NOT_RECOMMENDED: LedState.OFF,
}


def _ask_provider(provider: VisionProvider, image: bytes, mime_type: str, model: str | None) -> Decision:
    try:
        raw_response = provider.analyze(image, mime_type, model=model)
    except Exception:
        # Any provider failure must end as UNCERTAIN instead of leaving the analysis stuck.
        logger.exception("Vision provider %s failed", provider.name)
        return uncertain("The analysis service is unavailable right now.")
    return decide(raw_response)


def finish_interrupted_analyses() -> None:
    """Analyses still PROCESSING at startup were cut off by a restart; close them as UNCERTAIN."""
    with SessionLocal() as db:
        db.execute(
            update(Analysis)
            .where(Analysis.status == AnalysisStatus.PROCESSING)
            .values(
                status=AnalysisStatus.COMPLETED,
                recommendation=Recommendation.UNCERTAIN,
                uncertain_reason="The server restarted before the analysis finished.",
                completed_at=utcnow(),
            )
        )
        db.execute(
            update(HealthCheck)
            .where(HealthCheck.status.in_([HealthStatus.CHECKING, HealthStatus.REVIEWING]))
            .values(status=HealthStatus.REVIEW_UNAVAILABLE, completed_at=utcnow())
        )
        db.commit()


def run_analysis(
    analysis_id: str,
    image: bytes,
    mime_type: str,
    provider: VisionProvider,
    device_id: str,
    classifier: DiseaseClassifier,
    model: str | None = None,
    review_model: str | None = None,
) -> None:
    # The health check takes longer (it asks the AI to look closer), so it must not hold up the watering result or LED.
    with ThreadPoolExecutor(max_workers=1) as pool:
        health = pool.submit(run_health_check, analysis_id, image, mime_type, classifier, provider, review_model)
        _decide_watering(analysis_id, image, mime_type, provider, device_id, model)
        health.result()


def _decide_watering(
    analysis_id: str, image: bytes, mime_type: str, provider: VisionProvider, device_id: str, model: str | None
) -> None:
    decision = _ask_provider(provider, image, mime_type, model)
    now = utcnow()
    with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        result = decision.result
        if result is not None:
            analysis.plant_detected = result.plant_detected
            analysis.leaves_visible = result.leaves_visible
            analysis.image_quality = result.image_quality
            analysis.observations = result.observations
        if result is not None and decision.uncertain_reason is None:
            analysis.confidence_level = result.confidence_level
            analysis.explanation = result.explanation
            analysis.suggested_action = result.suggested_action
        analysis.recommendation = decision.recommendation
        analysis.uncertain_reason = decision.uncertain_reason

        led_state = _LED_STATES.get(decision.recommendation)
        if led_state is not None:
            create_led1_command(db, analysis.id, device_id, led_state, now)

        analysis.status = AnalysisStatus.COMPLETED
        analysis.completed_at = now
        db.commit()
