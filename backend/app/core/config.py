from pathlib import Path
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_SECRET_KEY_CONFIGURATION_ERROR = (
    "Production requires a non-placeholder SECRET_KEY with at least 32 characters."
)
_SECRET_KEY_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "change_this",
    "replace",
    "placeholder",
    "example",
    "your-secret",
    "your_secret",
    "<",
    ">",
)


class Settings(BaseSettings):
    database_url: str
    secret_key: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    environment: str = "development"
    access_token_expire_minutes: int = 30
    inference_model_path: Path | None = Field(default=None, validation_alias="FLORABOT_MODEL_PATH")
    camera_device_token: SecretStr | None = Field(default=None, validation_alias="FLORABOT_CAMERA_DEVICE_TOKEN")
    camera_plant_id: int | None = Field(default=None, validation_alias="FLORABOT_CAMERA_PLANT_ID")
    device_heartbeat_timeout_seconds: int = Field(
        default=180,
        ge=1,
        le=86400,
        validation_alias="FLORABOT_DEVICE_HEARTBEAT_TIMEOUT_SECONDS",
    )
    device_command_lease_seconds: int = Field(default=30, ge=1, le=3600, validation_alias="FLORABOT_DEVICE_COMMAND_LEASE_SECONDS")
    device_command_max_attempts: int = Field(default=3, ge=1, le=20, validation_alias="FLORABOT_DEVICE_COMMAND_MAX_ATTEMPTS")
    device_command_ttl_seconds: int = Field(default=300, ge=2, le=86400, validation_alias="FLORABOT_DEVICE_COMMAND_TTL_SECONDS")
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    def __init__(self, **values):
        super().__init__(**values)
        self._validate_production_secret_key()

    def _validate_production_secret_key(self) -> None:
        if self.environment.strip().casefold() not in {"production", "prod"}:
            return

        secret = self.secret_key.strip()
        normalized_secret = secret.casefold()
        is_placeholder = any(marker in normalized_secret for marker in _SECRET_KEY_PLACEHOLDER_MARKERS)
        has_low_character_variety = len(set(secret)) < 8
        if len(secret) < 32 or is_placeholder or has_low_character_variety:
            raise ValueError(_SECRET_KEY_CONFIGURATION_ERROR)

    @model_validator(mode="after")
    def validate_command_timeouts(self):
        if self.device_command_ttl_seconds <= self.device_command_lease_seconds:
            raise ValueError("Device command TTL must be longer than its delivery lease")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
