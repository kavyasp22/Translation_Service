# Translation Service change summary after the latest updates

This document lists the main code changes made to the translation service for:
- language normalization
- abbreviation and shortcut handling
- routing logic for native vs romanized/mixed text
- model-specific logging and request metadata
- benchmark/validation notes tied to the current implementation

It is intended as a reference map for anyone who downloaded this folder and wants to know exactly what changed and which files matter most when copying or replacing code.

## 1. Files changed and their purpose

### 1.1 Language canonicalization

# Changed file: app/utils/lang_codes.py

#### app/utils/lang_codes.py
Purpose:
- normalize backend-specific language strings into one canonical internal language code
- prevent duplicates like `en`, `eng`, `english` from being treated as separate values
- keep `my` and `burmese` separate
- map mixed labels like `hinglish`, `multilingual`, `romanized` into a single `mix` bucket

Primary changes:
- added `ALIASES_TO_CANONICAL`
- added `normalize_language_code(raw)`
- added `to_flores_code(iso_code)` for IndicTrans2-compatible codes
- canonicalization is used in routing, analytics, log fields, and response metadata

Impact:
- clean API responses
- consistent cache keys
- consistent logging and dashboard labels
- no duplicate language names in the UI analytics

---

### 1.2 Abbreviation and multilingual shortcut normalization

# Changed file: app/utils/abbreviation_normalizer.py

#### app/utils/abbreviation_normalizer.py
Purpose:
- expand common English social abbreviations such as `pls`, `tbh`, `asap`, `idk`
- support multilingual shortcut normalization for common informal terms in Hindi, Bengali, Punjabi, Assamese, Chinese, etc.
- keep canonical values in the same language rather than forcing English-only canonicalization

Primary changes:
- added `_ABBREVIATION_MAP` for English social shorthand
- added `_MULTILINGUAL_SHORTCUT_MAP` for same-language canonical forms
- added `normalize_multilingual_shortcut()`
- added `get_shortcut_metadata()`
- added `expand_common_english_abbreviations()`
- added `safe_expand_for_model()` with model-aware behavior

Design decision:
- same-language canonical value is preferred as the normalized representation
- English meaning is stored as metadata only, not as the primary canonical value
- model-specific behavior is conservative for IndicTrans2 to avoid aggressive rewriting of native Indic-script text

Impact:
- better handling of social text, slang, and transliterated content
- less confusion in mixed-language requests
- reduced risk of changing native Indic text incorrectly

---

### 1.3 Routing logic for native vs romanized vs mixed text

# Changed file: app/pipeline/language_router.py

#### app/pipeline/language_router.py
Purpose:
- decide which model chain to use for a request
- ensure Googletrans is only allowed for native-script text
- ensure Gemma is preferred for romanized and mixed-script input

Primary changes:
- added script-aware gating from `classify_routing()`
- `googletrans_allowed = script_type == "native"`
- if text is romanized or mixed: remove `googletrans` from the chain
- if script is Latin/transliterated: ensure `gemma` is moved to the front of the chain

Impact:
- prevents Googletrans from being used on romanized Hindi, Hinglish, or mixed-language content
- aligns with the intended routing policy: native script -> native-script models allowed; romanized/mixed -> Gemma first

---

### 1.4 Script detection and language heuristics

# Changed file: app/utils/script_detect.py

#### app/utils/script_detect.py
Purpose:
- detect whether the incoming text is native, Latin, or mixed
- estimate language and confidence from script + keyword heuristics
- keep routing decisions consistent before model invocation

Primary changes:
- added native-script range detection for many Indic scripts and other scripts
- added romanized Indic keyword detection for Hindi, Bengali, Punjabi, Pashto, Balochi, Divehi, etc.
- added `detect_script_type()` and `detect_romanized_indic()`
- added `classify_routing()` returning `script_type`, `detected_lang`, confidence, and `route_reason`

Impact:
- clean separation between native-language and transliterated text
- helps avoid sending Romanized/Hinglish inputs through Googletrans or IndicTrans2

---

### 1.5 Model pipeline behavior and request-level metadata logging

# Changed file: app/pipeline/translator_pipeline.py

#### app/pipeline/translator_pipeline.py
Purpose:
- normalize the source language before model selection
- pass the expanded text to the correct model
- log what language was requested, what was detected, which model was used, and which language each model call actually used

Primary changes:
- `prepared_text = safe_expand_for_model(prepared_text, "all", source_lang)`
- `routing["detected_lang"] = normalize_language_code(...)`
- `model_source_lang` is normalized before each backend call
- `final_detected` and `final_mixed_components` are normalized before response creation
- added logging like:
  - requested_source_lang
  - source_lang_auto_detected
  - normalized_source_lang
  - model_used
  - model_call_lang
  - model_detected_lang
  - mixed_components
  - script_type
  - route_reason
  - target_lang
  - latency_ms
  - cache_hit

Impact:
- gives clean, consistent logs for dashboard use
- separates raw backend behavior from canonical analytics values

---

### 1.6 API schema fields for metadata and response output

# Changed file: app/api/schemas.py

#### app/api/schemas.py
Purpose:
- expose the output fields needed by the dashboard and analytics layer

Relevant fields include:
- `detected_language`
- `mixed_components`
- `script_type`
- `route_reason`
- `model_used`
- `latency_ms`
- `cache_hit`

Impact:
- ensures the response payload matches the normalized metadata design

---

### 1.7 Model routing configuration

# Changed file: configs/language_models.yaml

#### configs/language_models.yaml
Purpose:
- explicitly define the model order for each known source language

Key behavior:
- native Indic languages list IndicTrans2 in the chain when the source is native-script Indic and target is English
- Googletrans is not treated as the default choice for romanized/mixed text
- Gemma is favored for romanized, mixed, or uncertain Latin-script text

Impact:
- route logic stays explicit and easy to reason about
- model selection becomes predictable

---

## 2. What changed in practice

These are the main implementation-level changes that matter most:

1. Canonical language normalization:
   - `en`, `eng`, `english` all collapse to `en`
   - `bn`, `ben`, `bengal`, `bengali` all collapse to `bn`
   - `myanmar` stays as `my`
   - `burmese` stays separate as `burmese`
   - mixed / hinglish / romanized labels collapse to `mix` when useful as a label

2. Abbreviation handling:
   - common English short forms are expanded before model call
   - multilingual shortcuts are normalized in the same-language canonical form
   - no aggressive rewrite for IndicTrans2 native-script inputs

3. Routing fix:
   - Googletrans is removed from non-native script calls
   - Gemma is preferred for Latin / romanized / mixed inputs

4. Logging fix:
   - logs now show the request language, normalized language, model used, model call language, detected language, mixed components, and route reason
   - this makes dashboard analytics reliable and easy to debug

5. Benchmark/validation notes:
   - tested with Gemma, Googletrans, and IndicTrans2 live paths
   - the document set in the `documents/` folder reflects the validation results and recommendations

---

## 3. Files most relevant to replacement or copy-over

If you are trying to port or replace the updated logic into another dashboard or service copy, these are the main files to keep together:

- app/utils/lang_codes.py
- app/utils/abbreviation_normalizer.py
- app/utils/script_detect.py
- app/pipeline/language_router.py
- app/pipeline/translator_pipeline.py
- app/api/schemas.py
- configs/language_models.yaml

Optional but relevant:
- app/models/googletrans_model.py
- app/models/indictrans2_model.py
- app/models/gemma_model.py
- app/models/base.py

---

## 4. Important design rule currently in use

The current implementation follows this principle:

- Native script input may use native-script models such as IndicTrans2 or Googletrans when relevant.
- Romanized or mixed-script input should be treated as a Gemma path.
- Dashboard and analytics should use canonical values, not raw backend labels.
- Mixed-language details should be stored as metadata, not used as the main canonical source-language value.

This is the key distinction between:
- the actual model input language used during translation
- the normalized request language used for analytics and reporting
- the mixed-language breakdown returned by the model for debugging and UI display

---

## 5. Recommended replacement summary for a dashboard integration

If you are integrating this into a different codebase or dashboard, replace the following concepts together:

- source language normalization
- abbreviation expansion
- script detection
- routing decision
- response schema for normalized language + model metadata
- logger fields for request and model-level tracking

Do not replace only the abbreviation map without the routing and normalization logic, because the service relies on all three together to behave correctly.

---

## 6. Current validated behavior

The implementation is currently aligned with this policy:

- Googletrans and IndicTrans2 are not the generic fallback for romanized or mixed-script text.
- Gemma is the preferred model for romanized and mixed-script cases.
- canonical language values are separated from raw detected labels and from model-reported mixed components.

This is the behavior that was tested, validated, and documented in the benchmark files under the `documents/` folder.
