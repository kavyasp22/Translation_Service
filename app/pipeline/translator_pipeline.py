"""
The orchestration layer. This is the single place that decides, for a given
request, which model runs first and what happens if it fails.

Routing itself lives in app/pipeline/language_router.py (language-specific
chains from configs/language_models.yaml, falling back to generic
script-based routing for anything not in that table). This module just
executes the resulting chain against the cache + circuit breaker.
"""
import logging
import time

from app.api.schemas import TranslateResponse
from app.core.cache import cache, make_cache_key
from app.models.registry import registry
from app.pipeline.circuit_breaker import circuit_breaker
from app.pipeline.language_router import get_routing_decision
from app.utils.abbreviation_normalizer import safe_expand_for_model
from app.utils.burmese_normalizer import prepare_for_translation
from app.utils.lang_codes import normalize_language_code

logger = logging.getLogger("translation_service.pipeline")


async def _try_model(model_name: str, text: str, source_lang: str, target_lang: str):
    """Returns a TranslationResult or raises. Respects the circuit breaker."""
    model = registry.get(model_name)
    if circuit_breaker.is_open(model_name):
        if await model.health_check():
            circuit_breaker.record_success(model_name)
        else:
            raise RuntimeError(f"circuit breaker open for {model_name}")

    try:
        result = await model.translate(text, source_lang, target_lang)
        circuit_breaker.record_success(model_name)
        return result
    except Exception as e:
        circuit_breaker.record_failure(model_name)
        logger.warning(f"{model_name} failed: {e}")
        raise


async def translate(text: str, source_lang: str, target_lang: str) -> TranslateResponse:
    start = time.monotonic()
    prepared_text = prepare_for_translation(text)
    prepared_text = safe_expand_for_model(prepared_text, "all", source_lang)

    cache_key = make_cache_key(prepared_text, source_lang, target_lang)
    cached = await cache.get(cache_key)
    if cached:
        cached["cache_hit"] = True
        cached["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
        return TranslateResponse(**cached)

    routing = get_routing_decision(prepared_text, source_lang, target_lang)
    routing["detected_lang"] = normalize_language_code(routing.get("detected_lang"))
    chain = routing["chain"]

    # IndicTrans2 has no real auto-detect capability - it needs the
    # already-resolved language, not the raw "auto" the caller may have
    # sent. Gemma is NOT included here - it handles "auto" itself, and its
    # own prompt does careful script/language disambiguation (Marathi vs
    # Hindi vs Nepali, etc.) specifically when it ISN'T given a hint,
    # explicitly skipping that reasoning if it is - forcing a routing-level
    # guess on it would make its detection worse, not better.
    MODELS_REQUIRING_RESOLVED_LANG = {"indictrans2"}

    last_error = None
    for position, model_name in enumerate(chain):
        # First entry uses the routing decision's real reason; every entry
        # after that is explicitly a fallback from whatever came before it.
        reason = routing["route_reason"] if position == 0 else f"fallback_from_{chain[position - 1]}"
        model_source_lang = (
            routing["detected_lang"]
            if source_lang == "auto" and model_name in MODELS_REQUIRING_RESOLVED_LANG
            else source_lang
        )
        model_source_lang = normalize_language_code(model_source_lang)
        try:
            model_input_text = safe_expand_for_model(prepared_text, model_name, model_source_lang)
            result = await _try_model(model_name, model_input_text, model_source_lang, target_lang)
            final_detected = normalize_language_code(result.detected_language or routing["detected_lang"])
            final_mixed_components = [
                normalize_language_code(component)
                for component in (result.mixed_components or [])
                if component
            ]
            response = TranslateResponse(
                translated_text=result.translated_text,
                detected_language=final_detected,
                corrected_text=result.corrected_text,
                pronunciation=result.pronunciation,
                mixed_components=final_mixed_components,
                script_type=routing["script_type"],
                route_reason=reason,
                model_used=model_name,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                cache_hit=False,
                entity_issues=result.entity_issues,
            )
            logger.info(
                "translation_success requested_source_lang=%s source_lang_auto_detected=%s normalized_source_lang=%s model_used=%s model_call_lang=%s model_detected_lang=%s mixed_components=%s script_type=%s route_reason=%s target_lang=%s latency_ms=%.2f cache_hit=%s",
                source_lang,
                routing["detected_lang"],
                final_detected,
                model_name,
                model_source_lang,
                result.detected_language or final_detected,
                final_mixed_components,
                routing["script_type"],
                reason,
                target_lang,
                response.latency_ms,
                False,
            )
            await cache.set(cache_key, response.model_dump())
            return response
        except Exception as e:
            last_error = e
            continue

    # Every model in the chain failed.
    raise RuntimeError(
        f"All translation backends failed for chain {chain}. Last error: {last_error}"
    )
