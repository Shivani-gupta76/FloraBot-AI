from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

CLASSES = {"Tomato_Healthy", "Tomato_Early_Blight", "Tomato_Late_Blight", "Tomato_Bacterial_Spot", "Tomato_Septoria", "Tomato_Leaf_Mold", "Tomato_Target_Spot", "Tomato_Mosaic_Virus", "Tomato_Yellow_Leaf_Curl_Virus", "Tomato_Spider_Mites", "Potato_Healthy", "Potato_Early_Blight", "Potato_Late_Blight", "Pepper_Healthy", "Pepper_Bacterial_Spot"}

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PlantIn(BaseModel):
    crop_type: str = Field(min_length=1, max_length=100)
    variety: str | None = None
    field_area: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    health_status: str | None = None
class PlantOut(ORMModel):
    id: int
    crop_type: str
    variety: str | None
    field_area: str | None
    latitude: float | None
    longitude: float | None
    health_status: str | None
    last_scanned_at: datetime | None
    last_watered_at: datetime | None
    created_at: datetime
    updated_at: datetime

class ConfidenceStatus(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    UNCERTAIN = "UNCERTAIN"
class DetectionIn(BaseModel):
    plant_id: int | None = None
    class_name: str
    confidence: float = Field(ge=0, le=1)
    confidence_status: ConfidenceStatus
    image_reference: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    detected_at: datetime
    model_version: str | None = None
    @model_validator(mode="after")
    def supported_class(self):
        if self.class_name not in CLASSES:
            raise ValueError("Unsupported Flora-Bot class")
        return self
class DetectionOut(ORMModel):
    id: int
    plant_id: int | None
    class_name: str
    confidence: float
    confidence_status: ConfidenceStatus
    image_reference: str | None
    latitude: float | None
    longitude: float | None
    detected_at: datetime
    model_version: str | None
    created_at: datetime

class SensorIn(BaseModel):
    robot_id: str = Field(min_length=1, max_length=100)
    sensor_type: str = Field(min_length=1, max_length=100)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    recorded_at: datetime
    @model_validator(mode="after")
    def validate_known_ranges(self):
        ranges = {"soil_moisture": (0, 100), "humidity": (0, 100), "water_level": (0, 100), "battery": (0, 100)}
        if self.sensor_type in ranges and not ranges[self.sensor_type][0] <= self.value <= ranges[self.sensor_type][1]:
            raise ValueError(f"{self.sensor_type} must be between 0 and 100")
        if self.sensor_type == "temperature" and not -100 <= self.value <= 100:
            raise ValueError("temperature is outside the accepted Celsius range")
        return self
class SensorOut(ORMModel):
    id: int
    robot_id: str
    sensor_type: str
    value: float
    unit: str
    recorded_at: datetime

class RobotState(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    SCANNING = "SCANNING"
    WATERING = "WATERING"
    LOW_BATTERY = "LOW_BATTERY"
    LOW_WATER = "LOW_WATER"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"

class TelemetryIn(BaseModel):
    robot_id: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    battery_level: float | None = Field(default=None, ge=0, le=100)
    water_tank_level: float | None = Field(default=None, ge=0, le=100)
    movement_status: str | None = None
    robot_state: RobotState | None = None
    recorded_at: datetime

class TelemetryOut(ORMModel):
    id: int
    robot_id: str
    latitude: float | None
    longitude: float | None
    battery_level: float | None
    water_tank_level: float | None
    movement_status: str | None
    robot_state: str | None
    recorded_at: datetime

class WateringIn(BaseModel):
    robot_id: str = Field(min_length=1, max_length=100)
    plant_id: int | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    water_amount_liters: float | None = Field(default=None, ge=0)
    trigger_source: str | None = None
    soil_moisture_before: float | None = Field(default=None, ge=0, le=100)
    soil_moisture_after: float | None = Field(default=None, ge=0, le=100)
    @model_validator(mode="after")
    def end_after_start(self):
        if self.ended_at and self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        return self
class WateringOut(ORMModel):
    id: int
    robot_id: str
    plant_id: int | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    water_amount_liters: float | None
    trigger_source: str | None
    soil_moisture_before: float | None
    soil_moisture_after: float | None
    created_at: datetime

class AlertOut(ORMModel):
    id: int
    alert_type: str
    message: str
    plant_id: int | None
    robot_id: str | None
    details: dict | None
    is_read: bool
    created_at: datetime
