from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_provider
from app.schemas import ModelChoiceOut, ModelOptionsOut
from app.vision.base import VisionProvider

router = APIRouter(prefix="/api/ai")


def checked_model(provider: VisionProvider, model: str | None) -> str | None:
    if model and model not in {choice.id for choice in provider.models}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This AI model isn't available.")
    return model or None


@router.get("/models")
def model_options(provider: VisionProvider = Depends(get_provider)) -> ModelOptionsOut:
    return ModelOptionsOut(
        choices=[ModelChoiceOut(id=c.id, label=c.label, description=c.description) for c in provider.models],
        default_model=provider.default_model,
        default_review_model=provider.default_review_model,
    )
