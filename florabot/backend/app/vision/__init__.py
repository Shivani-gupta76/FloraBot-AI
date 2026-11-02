from app.config import Settings
from app.vision.base import VisionProvider
from app.vision.gemini import GeminiProvider, gemini_client
from app.vision.mock import MockProvider


def build_provider(settings: Settings) -> VisionProvider:
    match settings.vision_provider:
        case "mock":
            return MockProvider(settings.mock_recommendation, settings.mock_delay_seconds)
        case "gemini":
            if settings.gemini_api_key is None:
                raise ValueError("Set FLORABOT_GEMINI_API_KEY to use the gemini provider")
            client = gemini_client(settings.gemini_api_key.get_secret_value(), settings.gemini_timeout_seconds)
            return GeminiProvider(client, settings.gemini_model, settings.gemini_review_model, settings.gemini_review_timeout_seconds)
    raise ValueError(f"Unknown vision provider: {settings.vision_provider!r}")
