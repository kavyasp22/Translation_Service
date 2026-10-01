# Model routing and script classification summary

This document captures how the Translation Service decides which backend to use and how it handles native, romanized, and mixed-language scripts.

## 1. Important distinction

The local project does not generate combined language labels like `hi-my-en`.

- `language` in the local project: a single detected language code such as `hi`, `en`, `bn`, `ta`, `ur`, `my`
- `detected_language` in the API response: a backend/model-returned field that may be passed through from an upstream model service as-is

The service only forwards the returned `detected_language` value if a model provides one. It does not build multi-part values locally.

## 2. Detection logic

The main logic lives in:
- `app/utils/script_detect.py`
- `app/pipeline/language_router.py`
- `configs/language_models.yaml`

### 2.1 Native vs Latin script detection

`detect_script_type()` checks the Unicode ranges and decides:
- `native` if a meaningful share of letters is in native script ranges (Devanagari, Bengali, Arabic, Tamil, Myanmar, etc.)
- `latin` otherwise

This is the first classification used by the router.

### 2.2 Romanized / transliterated detection

`detect_romanized_indic()` checks for Indic transliteration clues such as:
- `kaise`, `kya`, `aap`, `hain`
- `vanakkam`, `eppadi`, `nalla`
- etc.

If those appear in Latin script, the text is treated as romanized or transliterated input.

### 2.3 Mixed-language handling

If the text is Latin-script but not a clean English sentence, or contains mixed-language patterns, the route reason is treated as `romanized_or_mixed`.

This is the code path for Hinglish or other mixed-script inputs.

## 3. Model classification by script type

### Native script

If the text is in a native script and the language is recognized, the project routes using language-specific chains specified in `configs/language_models.yaml`.

Examples:
- Hindi -> IndicTrans2, Googletrans, Gemma
- Bengali -> IndicTrans2, Gemma, Googletrans
- Punjabi -> Gemma, IndicTrans2, Qwen, Googletrans
- Assamese -> Gemma, IndicTrans2, Googletrans
- Malayalam -> Gemma, IndicTrans2
- Burmese -> Gemma, Googletrans

### Romanized script

If text is in Latin script but transliterated or mixed, it is treated as romanized / mixed.

Behavior:
- Googletrans is normally excluded for this route
- Gemma is preferred because it handles transliteration and mixed-language text better than the specialized native-script engines

### Mixed script

Mixed-language inputs such as Latin-script Hindi + English phrases are treated as `romanized_or_mixed`.

Behavior:
- Prefer Gemma
- Do not rely on native-script-specific models like IndicTrans2

## 4. Model roles in this project

### Gemma

Role:
- Universal fallback
- Best model for romanized and mixed-script inputs
- Dominant general fallback for unknown language cases

Preferred cases:
- Latin-script transliterated text
- Hinglish / mixed-language text
- Unknown or unlisted languages
- Low-confidence native-script detection

### Qwen

Role:
- Specific fallback model configured for several language routes
- Used in selected native-language chains

Examples:
- Arabic
- Punjabi
- Baluchi

### IndicTrans2

Role:
- Indic-language specialist
- Mostly used for native Indic script text translated into English

Preferred cases:
- Hindi
- Bengali
- Nepali
- Assamese
- Malayalam
- Punjabi

## 5. Router decision logic

`get_routing_decision()` in `app/pipeline/language_router.py` does the following:

1. Detect script type and language via `classify_routing()`
2. Compute `googletrans_allowed = (script_type == "native")`
3. If `source_lang != "auto"`, use the manual override and prefer Gemma
4. If `source_lang == "auto"`, use detected language and route reason
5. If the language exists in the YAML chain, use that chain
6. If the text is Latin / mixed-script, promote Gemma to the front
7. If the language is not listed, fall back to generic script-based routing

This means:
- Native script -> native-language chains are used
- Romanized / mixed script -> Gemma is front-loaded
- Googletrans is blocked for non-native-script text in routing logic

## 6. Why `hi-my-en` is not produced by this project

The project’s local detection functions return a single best language code like `hi`, `en`, `bn`, etc. There is no internal logic that concatenates multiple codes into `hi-my-en`.

The code that can show a value like that is the field passed straight through from the backend/model response, such as:
- `output.get("detected_language")` in `app/models/googletrans_model.py`
- `res.src` in `node_backend/translate_darinrowe.js`

So a multi-tag value like `hi-my-en` indicates the upstream model or service returned it, and this service simply forwarded it.

## 7. Practical summary for leadership

- Local detection is single-language, script-aware, and route-based.
- Gemma is the flexible fallback for Latin / mixed / romanized text.
- IndicTrans2 is the specialized Indic native-script engine.
- Qwen is a configured fallback for selected languages.
- `hi-my-en` is not generated by the local detector; it is an upstream backend/model response value, not a project-created language classification.

## 8. Key files for reference

- `app/utils/script_detect.py`
- `app/pipeline/language_router.py`
- `configs/language_models.yaml`
- `app/models/gemma_model.py`
- `app/models/googletrans_model.py`
- `app/models/indictrans2_model.py`
- `app/models/qwen_model.py`
