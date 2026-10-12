import enum
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"


class ConfidenceStatus(str, enum.Enum):
    high_confidence = "HIGH_CONFIDENCE"
    review_recommended = "REVIEW_RECOMMENDED"
    uncertain = "UNCERTAIN"


class AlertType(str, enum.Enum):
    disease_detected = "DISEASE_DETECTED"
    low_confidence = "LOW_CONFIDENCE_DETECTION"
    dry_soil = "DRY_SOIL"
    low_water = "LOW_WATER"
    low_battery = "LOW_BATTERY"
    sensor_failure = "SENSOR_FAILURE"
    robot_offline = "ROBOT_OFFLINE"
    system_error = "SYSTEM_ERROR"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role", values_callable=lambda values: [value.value for value in values]), default=UserRole.operator)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = (CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90"), CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180"))
    id: Mapped[int] = mapped_column(primary_key=True)
    crop_type: Mapped[str] = mapped_column(String(100), index=True)
    variety: Mapped[str | None] = mapped_column(String(120))
    field_area: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    health_status: Mapped[str | None] = mapped_column(String(60))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_watered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    detections: Mapped[list["DiseaseDetection"]] = relationship(back_populates="plant")
    watering_events: Mapped[list["WateringEvent"]] = relationship(back_populates="plant")


class DiseaseDetection(Base):
    __tablename__ = "disease_detections"
    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 1"), CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90"), CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180"), Index("ix_detection_time_plant", "detected_at", "plant_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="SET NULL"), index=True)
    class_name: Mapped[str] = mapped_column(String(80), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_status: Mapped[ConfidenceStatus] = mapped_column(Enum(ConfidenceStatus, name="confidence_status", values_callable=lambda values: [value.value for value in values]))
    image_reference: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model_version: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    plant: Mapped[Plant | None] = relationship(back_populates="detections")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_robot_type_time", "robot_id", "sensor_type", "recorded_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[str] = mapped_column(String(100), index=True)
    sensor_type: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WateringEvent(Base):
    __tablename__ = "watering_events"
    __table_args__ = (CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0"), CheckConstraint("water_amount_liters IS NULL OR water_amount_liters >= 0"), Index("ix_watering_robot_start", "robot_id", "started_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[str] = mapped_column(String(100), index=True)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    water_amount_liters: Mapped[float | None] = mapped_column(Float)
    trigger_source: Mapped[str | None] = mapped_column(String(100))
    soil_moisture_before: Mapped[float | None] = mapped_column(Float)
    soil_moisture_after: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    plant: Mapped[Plant | None] = relationship(back_populates="watering_events")


class RobotTelemetry(Base):
    __tablename__ = "robot_telemetry"
    __table_args__ = (CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90"), CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180"), CheckConstraint("battery_level IS NULL OR battery_level BETWEEN 0 AND 100"), CheckConstraint("water_tank_level IS NULL OR water_tank_level BETWEEN 0 AND 100"), Index("ix_telemetry_robot_time", "robot_id", "recorded_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[str] = mapped_column(String(100), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    battery_level: Mapped[float | None] = mapped_column(Float)
    water_tank_level: Mapped[float | None] = mapped_column(Float)
    movement_status: Mapped[str | None] = mapped_column(String(80))
    robot_state: Mapped[str | None] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_created_unread", "is_read", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType, name="alert_type", values_callable=lambda values: [value.value for value in values]), index=True)
    message: Mapped[str] = mapped_column(Text)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="SET NULL"), index=True)
    robot_id: Mapped[str | None] = mapped_column(String(100), index=True)
    details: Mapped[dict | None] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
