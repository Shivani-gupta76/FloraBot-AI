from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    environment: str = "development"
    access_token_expire_minutes: int = 30
    inference_model_path: Path | None = Field(default=None, validation_alias="FLORABOT_MODEL_PATH")
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
