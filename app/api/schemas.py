from typing import Optional
from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to translate")
    source_lang: str = Field(default="auto", description="e.g. 'auto', 'hi', 'en'")
    target_lang: str = Field(default="en", description="e.g. 'en', 'hi'")


class TranslateResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    translated_text: str
    detected_language: Optional[str] = None
    corrected_text: Optional[str] = None
    pronunciation: Optional[str] = None
    mixed_components: list[str] = []

    # Metadata — useful for debugging/monitoring which path served the request
    script_type: str            # "native" | "latin"
    route_reason: str           # e.g. "native_script_high_confidence", "romanized_mixed", "primary_failed_fallback"
    model_used: str             # "gemma" | "indictrans2" | "qwen"
    latency_ms: float
    cache_hit: bool = False

    # Best-effort named-entity mismatch warnings (currently only populated when Gemma serves
    # the request - see gemma_engine.verify_entities). Empty list means either no issues found
    # or the serving backend doesn't run this check - not a guarantee of correctness either way.
    entity_issues: list[str] = []


class HealthResponse(BaseModel):
    status: str
    models: dict
