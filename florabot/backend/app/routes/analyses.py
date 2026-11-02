from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.analysis import run_analysis
from app.commands import device_online, expire_stale_commands
from app.db import get_db, utcnow
from app.deps import get_classifier, get_device, get_provider
from app.devices import DummyDevice, RealDevice
from app.disease import DiseaseClassifier, DiseasePrediction, confidence_level, describe, readable
from app.decision import Confidence
from app.images import MAX_BYTES, InvalidImage, validate_image
from app.messages import NO_COMMAND_MESSAGE, hardware_message, recommendation_message
from app.models import OPEN_COMMAND_STATUSES, Analysis, AnalysisStatus, CommandStatus, HealthCheck
from app.ratelimit import rate_limit
from app.routes.ai import checked_model
from app.schemas import AnalysisCreatedOut, AnalysisOut, HardwareOut, HealthOut, HealthReviewOut, LeafAssessmentOut
from app.vision.base import VisionProvider

router = APIRouter(prefix="/api/analyses")


@router.post("", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(rate_limit("analyses"))])
def create_analysis(
    image: UploadFile,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    provider: VisionProvider = Depends(get_provider),
    device: RealDevice | DummyDevice = Depends(get_device),
    classifier: DiseaseClassifier = Depends(get_classifier),
    model: str | None = Form(default=None),
    review_model: str | None = Form(default=None),
) -> AnalysisCreatedOut:
    model = checked_model(provider, model)
    review_model = checked_model(provider, review_model)
    data = image.file.read(MAX_BYTES + 1)
    try:
        mime_type = validate_image(image.filename or "", image.content_type or "", data)
    except InvalidImage as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    analysis = Analysis(provider=provider.name, health=HealthCheck())
    db.add(analysis)
    db.commit()
    background.add_task(
        run_analysis, analysis.id, data, mime_type, provider, device.device_id, classifier, model, review_model
    )
    return AnalysisCreatedOut(analysis_id=analysis.id, status=analysis.status)


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    device: RealDevice | DummyDevice = Depends(get_device),
) -> AnalysisOut:
    now = utcnow()
    expire_stale_commands(db, now)
    db.commit()
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This analysis was not found. Please upload the photo again.")

    completed = analysis.status is AnalysisStatus.COMPLETED
    return AnalysisOut(
        analysis_id=analysis.id,
        status=analysis.status,
        provider=analysis.provider,
        recommendation=analysis.recommendation,
        plant_detected=analysis.plant_detected,
        leaves_visible=analysis.leaves_visible,
        image_quality=analysis.image_quality,
        observations=analysis.observations,
        confidence_level=analysis.confidence_level,
        explanation=analysis.explanation,
        suggested_action=analysis.suggested_action,
        uncertain_reason=analysis.uncertain_reason,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
        message=recommendation_message(analysis) if completed else None,
        hardware=_hardware(db, analysis, device, now) if completed else None,
        health=_health(analysis.health),
    )


def _health(check: HealthCheck | None) -> HealthOut | None:
    if check is None:
        return None
    initial = None
    if check.leaf_label is not None:
        crop, condition = readable(check.leaf_label)
        level = confidence_level(check.leaf_confidence)
        initial = LeafAssessmentOut(
            crop=crop,
            condition=condition,
            healthy=condition == "Healthy",
            confidence_level=level,
            confident=level is Confidence.HIGH,
            message=describe(DiseasePrediction(check.leaf_label, check.leaf_confidence, check.leaf_alternatives)),
            alternatives=[" · ".join(readable(label)) for label in check.leaf_alternatives],
        )
    review = HealthReviewOut(**check.review) if check.review else None
    return HealthOut(status=check.status, initial=initial, review=review)


def _hardware(db: Session, analysis: Analysis, device: RealDevice | DummyDevice, now: datetime) -> HardwareOut:
    command = analysis.command
    if command is None:
        return HardwareOut(
            command_status=None,
            requested_state=None,
            confirmed_state=None,
            message=NO_COMMAND_MESSAGE,
            final=True,
            expires_at=None,
        )
    online = device_online(db, device.device_id, now)
    return HardwareOut(
        command_status=command.status,
        requested_state=command.requested_state,
        confirmed_state=command.acknowledged_state if command.status is CommandStatus.ACKNOWLEDGED else None,
        message=hardware_message(command, online, device.simulated),
        final=command.status not in OPEN_COMMAND_STATUSES,
        expires_at=command.expires_at,
    )
