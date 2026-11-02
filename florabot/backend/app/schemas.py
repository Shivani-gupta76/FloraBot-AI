from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.config import DeviceMode
from app.decision import Confidence, ImageQuality, Recommendation
from app.devices import SimulationBehaviour
from app.models import AnalysisStatus, CommandStatus, HealthStatus, LedState


class AnalysisCreatedOut(BaseModel):
    analysis_id: str
    status: AnalysisStatus


class HardwareOut(BaseModel):
    command_status: CommandStatus | None
    requested_state: LedState | None
    confirmed_state: LedState | None
    message: str
    final: bool
    expires_at: datetime | None


class HealthReviewOut(BaseModel):
    plant: str
    finding: str
    problem: str
    # Reviews saved before this field existed have none.
    possible_causes: list[str] = []
    confidence_level: Confidence
    agrees_with_leaf_model: bool
    observations: list[str]
    advice: str


class LeafAssessmentOut(BaseModel):
    """The local leaf model's initial assessment."""

    crop: str
    condition: str
    healthy: bool
    confidence_level: Confidence
    # True only for HIGH confidence; anything lower is shown as a possibility.
    confident: bool
    message: str
    alternatives: list[str]


class HealthOut(BaseModel):
    status: HealthStatus
    initial: LeafAssessmentOut | None
    review: HealthReviewOut | None


class AnalysisOut(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    provider: str
    recommendation: Recommendation | None
    plant_detected: bool | None
    leaves_visible: bool | None
    image_quality: ImageQuality | None
    observations: list[str]
    confidence_level: Confidence | None
    explanation: str | None
    suggested_action: str | None
    uncertain_reason: str | None
    created_at: datetime
    completed_at: datetime | None
    message: str | None
    hardware: HardwareOut | None
    health: HealthOut | None


class DeviceCommandOut(BaseModel):
    command_id: str
    device_id: str
    led: str
    requested_state: LedState
    created_at: datetime
    expires_at: datetime


class PollOut(BaseModel):
    command: DeviceCommandOut | None


class AckIn(BaseModel):
    device_id: str
    success: bool
    led_state: LedState


class AckOut(BaseModel):
    command_id: str
    status: CommandStatus


class DeviceCommandView(BaseModel):
    command_id: str
    analysis_id: str
    led: str
    requested_state: LedState
    status: CommandStatus
    created_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_state: LedState | None
    failure: str | None


class SimulationOut(BaseModel):
    behaviour: SimulationBehaviour
    response_delay_seconds: float


class HardwareStatusOut(BaseModel):
    mode: DeviceMode
    device_id: str
    label: str
    online: bool
    last_seen_at: datetime | None
    led1_state: LedState | None
    simulation: SimulationOut | None
    pending_command: DeviceCommandView | None


class SimulationIn(BaseModel):
    behaviour: SimulationBehaviour
    response_delay_seconds: float = Field(ge=0, le=20)


class ManualAckIn(BaseModel):
    success: bool


class CareQuestionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=2, max_length=500)
    model: str | None = None


class CareAnswerOut(BaseModel):
    answer: str
    provider: str


class ModelChoiceOut(BaseModel):
    id: str
    label: str
    description: str


class ModelOptionsOut(BaseModel):
    # Empty when the AI provider offers no choice (for example the mock).
    choices: list[ModelChoiceOut]
    default_model: str | None
    default_review_model: str | None


class ConnectOut(BaseModel):
    url: str | None
    # False when the server only listens on 127.0.0.1, so a phone could not open the URL.
    reachable: bool
