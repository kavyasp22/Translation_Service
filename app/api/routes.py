import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import TranslateRequest, TranslateResponse, HealthResponse
from app.models.registry import registry
from app.pipeline import translator_pipeline

logger = logging.getLogger("translation_service.routes")

router = APIRouter()


@router.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest) -> TranslateResponse:
    try:
        return await translator_pipeline.translate(
            request.text, request.source_lang, request.target_lang
        )
    except Exception as e:
        logger.error(f"Translation failed entirely: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    snapshot = await registry.health_snapshot()
    overall = "ok" if any(snapshot.values()) else "degraded"
    return HealthResponse(status=overall, models=snapshot)
