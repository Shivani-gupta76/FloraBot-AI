"""Disease alert decisions and their independent LED2 command side effects."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertType,
    ConfidenceStatus,
    Device,
    DeviceCommand,
    DeviceCommandStatus,
    DiseaseDetection,
    LedChannel,
    LedDesiredState,
)
from app.schemas import DeviceCommandCreateIn
from app.services.device_commands import create_device_command

logger = logging.getLogger(__name__)


def _is_healthy(class_name: str) -> bool:
    return class_name.endswith("_Healthy")


def disease_led2_action(
    db: Session,
    plant_id: int | None,
    class_name: str,
    confidence_status: str | ConfidenceStatus,
) -> str | None:
    """Return ON for a confident disease, OFF for a confirmed active alert cleared by healthy.

    Review-required and uncertain observations do not change the desired LED state.
    An alert is considered active when the latest decisive detection is a confident
    disease detection and its disease alert exists. Alert ``is_read`` is not used
    as a resolution marker because reading an alert does not clear the condition.
    """
    confidence_value = getattr(confidence_status, "value", confidence_status)
    if confidence_value != ConfidenceStatus.high_confidence.value:
        return None
    if not _is_healthy(class_name):
        return "ON"
    if plant_id is None:
        return None

    latest_decisive = db.scalar(
        select(DiseaseDetection)
        .where(
            DiseaseDetection.plant_id == plant_id,
            DiseaseDetection.confidence_status == ConfidenceStatus.high_confidence,
        )
        .order_by(DiseaseDetection.created_at.desc(), DiseaseDetection.id.desc())
        .limit(1)
    )
    if latest_decisive is None or _is_healthy(latest_decisive.class_name):
        return None

    disease_alerts = db.scalars(
        select(Alert).where(
            Alert.plant_id == plant_id,
            Alert.alert_type == AlertType.disease_detected,
        )
    ).all()
    if any(
        isinstance(alert.details, dict)
        and str(alert.details.get("detection_id")) == str(latest_decisive.id)
        for alert in disease_alerts
    ):
        return "OFF"
    return None


def enqueue_disease_led2_command(
    db: Session,
    detection: DiseaseDetection,
    desired_state: str,
) -> int:
    """Queue one idempotent LED2 desired state per enabled, credentialed plant device.

    The detection and alert have already been committed. A command failure is logged
    safely and does not roll back or hide the detection record.
    """
    if desired_state not in {"ON", "OFF"} or detection.plant_id is None:
        return 0

    try:
        devices = db.scalars(
            select(Device).where(
                Device.plant_id == detection.plant_id,
                Device.enabled.is_(True),
                Device.credential_revoked_at.is_(None),
            )
        ).all()
    except Exception as error:
        db.rollback()
        logger.error(
            "LED2 command enqueue failed for detection_id=%s error_type=%s",
            detection.id,
            type(error).__name__,
        )
        return 0
    queued = 0
    for device in devices:
        try:
            latest_led2 = db.scalar(
                select(DeviceCommand)
                .where(
                    DeviceCommand.device_id == device.id,
                    DeviceCommand.led_channel == LedChannel.LED2,
                )
                .order_by(DeviceCommand.created_at.desc(), DeviceCommand.command_id.desc())
                .limit(1)
            )
            if (
                desired_state == "ON"
                and latest_led2 is not None
                and latest_led2.desired_state == LedDesiredState.ON
                and latest_led2.status
                in {
                    DeviceCommandStatus.PENDING,
                    DeviceCommandStatus.DELIVERED,
                    DeviceCommandStatus.ACKNOWLEDGED,
                }
            ):
                # Repeated confirmed uploads while the disease condition is active do not
                # enqueue another ON command while an earlier ON is pending or confirmed.
                continue
            data = DeviceCommandCreateIn(
                led_channel="LED2",
                desired_state=desired_state,
                source="DISEASE_DETECTION",
                reason=(
                    f"Confirmed disease detection: {detection.class_name}"
                    if desired_state == "ON"
                    else "Confirmed healthy follow-up cleared the active disease alert"
                ),
                idempotency_key=f"disease-detection-{detection.id}-led2",
            )
            _command, created = create_device_command(db, device, data)
            queued += int(created)
        except Exception as error:
            # Keep logs useful while avoiding database exception strings or other sensitive details.
            db.rollback()
            logger.error(
                "LED2 command enqueue failed for detection_id=%s device_id=%s error_type=%s",
                detection.id,
                device.id,
                type(error).__name__,
            )
    return queued
