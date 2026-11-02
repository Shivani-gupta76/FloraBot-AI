from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.decision import Recommendation


class DeviceMode(StrEnum):
    REAL = "real"
    DUMMY = "dummy"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLORABOT_", env_file=".env", env_ignore_empty=True, extra="ignore")

    device_mode: DeviceMode = DeviceMode.DUMMY
    device_token: SecretStr | None = None
    device_id: str = "esp32-led1"
    database_url: str = "sqlite:///./florabot.db"
    vision_provider: str = "mock"
    mock_recommendation: Recommendation = Recommendation.WATERING_RECOMMENDED
    mock_delay_seconds: float = Field(default=1.5, ge=0, le=30)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_timeout_seconds: int = Field(default=30, ge=5, le=300)
    # Model for the closer plant-health look. It runs next to the watering decision, so a stronger, slower model
    # (gemini-flash-latest, or Pro on a paid plan) can be set here without delaying the LED.
    gemini_review_model: str = "gemini-flash-lite-latest"
    gemini_review_timeout_seconds: int = Field(default=90, ge=5, le=300)
    disease_classifier: str = "yolo"
    disease_model_path: Path = Path(__file__).resolve().parents[1] / "models" / "flora_bot_best.pt"
    command_ttl_seconds: int = Field(default=30, ge=5)
    device_offline_seconds: int = Field(default=15, ge=5)
    rate_limit_per_minute: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def require_token_for_real_device(self):
        token = self.device_token.get_secret_value() if self.device_token else ""
        if self.device_mode is DeviceMode.REAL and len(token) < 16:
            raise ValueError("Set FLORABOT_DEVICE_TOKEN (at least 16 characters) when FLORABOT_DEVICE_MODE=real")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
