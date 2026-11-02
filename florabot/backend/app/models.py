from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow
from app.decision import Confidence, ImageQuality, Recommendation


def new_id() -> str:
    return str(uuid4())


class AnalysisStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


OPEN_COMMAND_STATUSES = (CommandStatus.PENDING, CommandStatus.DELIVERED)


class HealthStatus(StrEnum):
    CHECKING = "CHECKING"
    REVIEWING = "REVIEWING"
    DONE = "DONE"
    REVIEW_UNAVAILABLE = "REVIEW_UNAVAILABLE"


class LedState(StrEnum):
    ON = "ON"
    OFF = "OFF"


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[AnalysisStatus] = mapped_column(default=AnalysisStatus.PROCESSING)
    provider: Mapped[str] = mapped_column(String(40))
    plant_detected: Mapped[bool | None]
    leaves_visible: Mapped[bool | None]
    image_quality: Mapped[ImageQuality | None]
    observations: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommendation: Mapped[Recommendation | None]
    confidence_level: Mapped[Confidence | None]
    explanation: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    uncertain_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    command: Mapped["Command | None"] = relationship(back_populates="analysis")
    health: Mapped["HealthCheck | None"] = relationship(back_populates="analysis")


class HealthCheck(Base):
    """The plant-health check for a photo: the local leaf model's result, then the AI provider's closer look."""

    __tablename__ = "health_checks"

    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), primary_key=True)
    status: Mapped[HealthStatus] = mapped_column(default=HealthStatus.CHECKING)
    leaf_label: Mapped[str | None] = mapped_column(String(64))
    leaf_confidence: Mapped[float | None]
    leaf_alternatives: Mapped[list[str]] = mapped_column(JSON, default=list)
    review: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    analysis: Mapped[Analysis] = relationship(back_populates="health")


class Command(Base):
    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), unique=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    led: Mapped[str] = mapped_column(String(8), default="LED1")
    requested_state: Mapped[LedState]
    status: Mapped[CommandStatus] = mapped_column(default=CommandStatus.PENDING, index=True)
    acknowledged_state: Mapped[LedState | None]
    failure: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    analysis: Mapped[Analysis] = relationship(back_populates="command")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
