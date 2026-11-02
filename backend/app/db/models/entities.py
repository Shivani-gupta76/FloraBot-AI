import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func, text
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


class LedChannel(str, enum.Enum):
    LED1 = "LED1"
    LED2 = "LED2"


class LedDesiredState(str, enum.Enum):
    ON = "ON"
    OFF = "OFF"


class DeviceCommandStatus(str, enum.Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


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
    devices: Mapped[list["Device"]] = relationship(back_populates="plant")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("device_identifier", name="uq_devices_device_identifier"),
        UniqueConstraint("credential_hash", name="uq_devices_credential_hash"),
        UniqueConstraint("id", "plant_id", name="uq_devices_id_plant_id"),
        CheckConstraint("length(trim(device_identifier)) > 0", name="ck_devices_identifier_nonempty"),
        CheckConstraint("length(trim(device_name)) > 0", name="ck_devices_name_nonempty"),
        CheckConstraint("credential_version >= 1", name="ck_devices_credential_version_positive"),
        Index("ix_devices_enabled_last_seen", "enabled", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    device_name: Mapped[str] = mapped_column(String(160), nullable=False)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", name="fk_devices_plant_id_plants", ondelete="RESTRICT"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # Store only a one-way token verifier, never the provisioned device token.
    credential_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    credential_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credential_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plant: Mapped["Plant"] = relationship(back_populates="devices")
    commands: Mapped[list["DeviceCommand"]] = relationship(
        back_populates="device",
        foreign_keys=lambda: [DeviceCommand.device_id, DeviceCommand.plant_id],
    )


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    __table_args__ = (
        ForeignKeyConstraint(
            ["device_id", "plant_id"],
            ["devices.id", "devices.plant_id"],
            name="fk_device_commands_device_plant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["plant_id"], ["plants.id"], name="fk_device_commands_plant", ondelete="RESTRICT"),
        UniqueConstraint("device_id", "idempotency_key", name="uq_device_commands_device_idempotency"),
        CheckConstraint("led_channel IN ('LED1', 'LED2')", name="ck_device_commands_led_channel"),
        CheckConstraint("desired_state IN ('ON', 'OFF')", name="ck_device_commands_desired_state"),
        CheckConstraint(
            "(led_channel = 'LED1' AND command_source = 'WATERING_ASSISTANT') OR "
            "(led_channel = 'LED2' AND command_source = 'DISEASE_DETECTION')",
            name="ck_device_commands_channel_source",
        ),
        CheckConstraint("status IN ('PENDING', 'DELIVERED', 'ACKNOWLEDGED', 'FAILED', 'EXPIRED')", name="ck_device_commands_status"),
        CheckConstraint("length(trim(command_source)) > 0", name="ck_device_commands_source_nonempty"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_device_commands_idempotency_nonempty"),
        CheckConstraint("attempt_count >= 0", name="ck_device_commands_attempt_count_nonnegative"),
        CheckConstraint("expires_at > created_at", name="ck_device_commands_expiry_after_creation"),
        CheckConstraint("acknowledged_at IS NULL OR delivered_at IS NOT NULL", name="ck_device_commands_ack_requires_delivery"),
        CheckConstraint("status != 'DELIVERED' OR delivered_at IS NOT NULL", name="ck_device_commands_delivered_timestamp"),
        CheckConstraint("status != 'ACKNOWLEDGED' OR acknowledged_at IS NOT NULL", name="ck_device_commands_ack_timestamp"),
        CheckConstraint("status != 'FAILED' OR failure_code IS NOT NULL", name="ck_device_commands_failure_code"),
        Index("ix_device_commands_device_status_created", "device_id", "status", "created_at"),
        Index("ix_device_commands_status_expires", "status", "expires_at"),
    )

    command_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    plant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    led_channel: Mapped[LedChannel] = mapped_column(
        Enum(LedChannel, name="device_command_led_channel", native_enum=False, create_constraint=False, validate_strings=True, values_callable=lambda values: [value.value for value in values]),
        nullable=False,
    )
    desired_state: Mapped[LedDesiredState] = mapped_column(
        Enum(LedDesiredState, name="device_command_desired_state", native_enum=False, create_constraint=False, validate_strings=True, values_callable=lambda values: [value.value for value in values]),
        nullable=False,
    )
    command_source: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[DeviceCommandStatus] = mapped_column(
        Enum(DeviceCommandStatus, name="device_command_status", native_enum=False, create_constraint=False, validate_strings=True, values_callable=lambda values: [value.value for value in values]),
        nullable=False,
        default=DeviceCommandStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    # Store a short sanitized code/message only; never persist device tokens or raw stack traces here.
    failure_detail: Mapped[str | None] = mapped_column(String(255))

    device: Mapped["Device"] = relationship(back_populates="commands", foreign_keys=[device_id, plant_id])


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


class CameraUploadRequest(Base):
    """Optional camera upload idempotency records; image bytes are never stored."""
    __tablename__ = "camera_upload_requests"
    __table_args__ = (
        UniqueConstraint("plant_id", "idempotency_key", name="uq_camera_upload_plant_key"),
        UniqueConstraint("detection_id", name="uq_camera_upload_detection"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_camera_upload_key_nonempty"),
        CheckConstraint("length(image_sha256) = 64", name="ck_camera_upload_hash_length"),
        Index("ix_camera_upload_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    detection_id: Mapped[int] = mapped_column(ForeignKey("disease_detections.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())


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
