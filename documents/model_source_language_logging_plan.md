# Model Source-Language Logging Plan

## Goal

We need logs that answer two questions clearly:

1. What is the normalized source language for each translation request?
2. Which model actually translated it, and what language was used for that model call?

The current duplication problem happens because different detectors and models emit different labels for the same language, such as:

- `en`, `eng`, `english`
- `bn`, `bengal`, `bengali`
- `hi`, `hin`, `hindi`
- `my`, `mya`, `burmese`
- `zh`, `zh-cn`, `zh-tw`
- `mixed`, `multilingual`, `hinglish`
- `und`, `unknown`

These must be normalized before counting or logging.

---

## Required logging fields

For every translation event, log these fields:

- `request_id`
- `text_preview`
- `requested_source_lang`
- `source_lang_auto_detected`
- `normalized_source_lang`
- `script_type`
- `route_reason`
- `model_chain_attempted`
- `model_used`
- `model_call_lang`
- `model_detected_lang`
- `target_lang`
- `status` (`success` / `fallback` / `failed`)
- `latency_ms`
- `cache_hit`
- `raw_detected_language` (debug-only metadata)

This ensures we have both:

- canonical language analytics
- per-model performance and routing visibility

---

## Example event structure

Example final log lines should look like this:

- `request_id=abc123 requested_source_lang=auto source_lang_auto_detected=hi normalized_source_lang=hi model_used=indictrans2 model_call_lang=hi model_detected_lang=hi script_type=native route_reason=native_script_high_confidence model_chain_attempted=[indictrans2,googletrans,gemma] target_lang=en status=success latency_ms=420 cache_hit=false`

- `request_id=abc124 requested_source_lang=auto source_lang_auto_detected=en normalized_source_lang=en model_used=gemma model_call_lang=en model_detected_lang=en script_type=latin route_reason=transliterated_latin_route:en model_chain_attempted=[gemma] target_lang=en status=success latency_ms=230 cache_hit=false`

- `request_id=abc125 requested_source_lang=auto source_lang_auto_detected=mix normalized_source_lang=mix model_used=gemma model_call_lang=mix model_detected_lang=mix script_type=latin route_reason=romanized_or_mixed model_chain_attempted=[gemma] target_lang=en status=success latency_ms=310 cache_hit=false`

---

## Required model-specific logging behavior

### 1. Gemma

Log:

- `source_lang` as the user value or the resolved route value
- `normalized_source_lang` after alias normalization
- `script_type`
- `model_used=gemma`

Gemma is expected to handle:

- native script
- latin/romanized text
- mixed-script text

### 2. Googletrans

Log:

- only when route allows it
- only for native-script requests
- `normalized_source_lang`
- `model_used=googletrans`

Googletrans should not be used for romanized or mixed text.

### 3. IndicTrans2

Log:

- the resolved source language before API call
- `normalized_source_lang`
- `model_used=indictrans2`

IndicTrans2 should only be used for supported Indic language pairs and only when `target_lang == "en"` in this repo.

### 4. Qwen

Log:

- the language value selected by the chain
- `normalized_source_lang`
- `model_used=qwen`

---

## Required aggregate counters

We should compute these two counter sets separately:

### A. Language counts by normalized code

- `language_counts["hi"] += 1`
- `language_counts["bn"] += 1`
- `language_counts["en"] += 1`
- `language_counts["mix"] += 1`
- `language_counts["und"] += 1`

### B. Model + language counts

- `model_language_counts["gemma"]["en"] += 1`
- `model_language_counts["gemma"]["mix"] += 1`
- `model_language_counts["indictrans2"]["hi"] += 1`
- `model_language_counts["googletrans"]["bn"] += 1`

This gives both of these answers:

- Which language is most common overall?
- Which model handled which language?

---

## Logging implementation plan before code changes

1. Add a single normalizer in [translation_service/app/utils/lang_codes.py](../app/utils/lang_codes.py)
   - function: `normalize_language_code(raw)`
   - map alias variations to one canonical code
   - collapse `unknown`, `und`, `mixed`, `multilingual`, `hinglish` into canonical buckets

2. Add logging at the pipeline boundary in [translation_service/app/pipeline/translator_pipeline.py](../app/pipeline/translator_pipeline.py)
   - before model call: log requested and detected values
   - after final success: log final model and normalized language

3. Add logging in each model wrapper
   - model-specific debug logs can be added in:
     - [translation_service/app/models/gemma_model.py](../app/models/gemma_model.py)
     - [translation_service/app/models/googletrans_model.py](../app/models/googletrans_model.py)
     - [translation_service/app/models/indictrans2_model.py](../app/models/indictrans2_model.py)
     - [translation_service/app/models/qwen_model.py](../app/models/qwen_model.py)

4. Keep raw labels separate from canonical metrics
   - `raw_detected_language` = debug metadata only
   - `normalized_source_lang` = analytics and reporting field

5. Add tests for the following cases:
   - `en`, `eng`, `english` => `en`
   - `bn`, `bengal`, `bengali` => `bn`
   - `hi`, `hin`, `hindi` => `hi`
   - `my`, `mya`, `burmese` => `my`
   - `zh-cn`, `zh-tw` => `zh`
   - `mixed`, `multilingual`, `hinglish` => `mix`
   - `unknown`, `und` => `und`

---

## Final expected behavior

After implementation, the logs should be structured like this:

- normalized language counts
- model counts
- model-language counts
- route reason and script type included
- raw alias values kept only for debugging

This gives a clean answer to both:

- “Which language had the highest volume?”
- “Which model handled which language?”

This is the correct logging design before implementing the actual code changes.
