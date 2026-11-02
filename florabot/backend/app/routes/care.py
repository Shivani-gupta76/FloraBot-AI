import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_provider
from app.ratelimit import rate_limit
from app.routes.ai import checked_model
from app.schemas import CareAnswerOut, CareQuestionIn
from app.vision.base import VisionProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/care")

CARE_UNAVAILABLE = "The plant-care assistant is unavailable right now. Please try again in a moment."


@router.post("/answers", dependencies=[Depends(rate_limit("care"))])
def answer_question(question: CareQuestionIn, provider: VisionProvider = Depends(get_provider)) -> CareAnswerOut:
    model = checked_model(provider, question.model)
    try:
        answer = provider.answer_question(question.question, model=model).strip()
    except Exception as error:
        logger.exception("Vision provider %s could not answer a care question", provider.name)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CARE_UNAVAILABLE) from error
    if not answer:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CARE_UNAVAILABLE)
    return CareAnswerOut(answer=answer, provider=provider.name)
