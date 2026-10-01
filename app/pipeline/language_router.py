"""
Decides the ordered list of model backends to try for a given request.

Two routing modes:
  1. LANGUAGE-SPECIFIC: if the detected (or user-declared) source language
     has an entry in configs/language_models.yaml, use that exact chain
     (this is where your Gemma/IndicTrans2/Qwen/Googletrans table lives).
  2. GENERIC: for any language not in that table, choose between Googletrans
     and Gemma based on script/confidence (see app/utils/script_detect.py) -
     native script + high confidence tries the (free, but unofficial and
     rate-limitable) Googletrans scraper first; low-confidence native script
     goes to Gemma first instead (Googletrans is still available as a
     fallback there - the text is still genuinely native-script, just an
     uncertain language guess).

Googletrans is NEVER used for romanized or mixed-script text (script_type ==
"latin" - this covers plain romanized text, code-mixed/Hinglish-style input,
and even a manual source_lang override when the actual text is Latin
script), in either routing mode - confirmed on real examples (e.g. romanized
Burmese) that the scraper does noticeably worse than Gemma there, often
misdetecting the language entirely. It's dropped from the chain outright
rather than just de-prioritized, so it's never even tried as a fallback on
that kind of input.
"""
from app.core.config import get_language_routing_config
from app.utils.script_detect import classify_routing


def get_routing_decision(text: str, source_lang: str, target_lang: str) -> dict:
    detected = classify_routing(text)
    script_type = detected["script_type"]
    # See module docstring - Googletrans is only ever a candidate for
    # genuinely native-script text, regardless of routing mode or
    # source_lang override.
    googletrans_allowed = script_type == "native"

    if source_lang != "auto":
        lang_code = source_lang
        base_reason = f"manual_source_lang_override:{lang_code}"
        # No script/confidence signal available for a manually-declared
        # language, so default to Gemma first rather than the unofficial
        # googletrans scraper.
        use_gemma_first = True
    else:
        lang_code = detected["detected_lang"]
        base_reason = detected["route_reason"]
        use_gemma_first = base_reason != "native_script_high_confidence"

    routing_config = get_language_routing_config()
    lang_chains = routing_config.get("language_fallback_chains", {})

    if lang_code in lang_chains:
        chain = list(lang_chains[lang_code])
        if not googletrans_allowed:
            chain = [m for m in chain if m != "googletrans"]
        # For transliterated / Latin script text (e.g. Hinglish), promote Gemma to 1st priority
        if script_type == "latin" and "gemma" in chain:
            chain.remove("gemma")
            chain.insert(0, "gemma")
            route_reason = f"transliterated_latin_route:{lang_code}"
        else:
            route_reason = f"language_specific_route:{lang_code}"
    elif not googletrans_allowed:
        chain = ["gemma"]
        route_reason = base_reason
    else:
        chain = ["gemma", "googletrans"] if use_gemma_first else ["googletrans", "gemma"]
        route_reason = base_reason

    return {
        "chain": chain,
        "script_type": script_type,
        "detected_lang": lang_code,
        "route_reason": route_reason,
    }
