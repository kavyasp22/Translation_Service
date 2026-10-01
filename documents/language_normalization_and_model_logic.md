# Language Normalization and Model Routing Notes

## Why the same language appears many times with different names

This is happening because the service currently allows multiple backends and detectors to emit different language labels for the same underlying language, without normalizing them into one canonical code before logging or aggregation.

Examples from the current pipeline:

- `en`, `eng`, `english`
- `bn`, `bengal`, `bengali`
- `hi`, `hin`, `hindi`
- `my`, `mya`, `burmese`
- `zh`, `zh-cn`, `zh-tw`
- `mixed`, `multilingual`, `hinglish`, `hinglish-burmese mixed`
- `und`, `unknown`

This is not a Unicode bug. It is a canonicalization issue.

The relevant code paths are:

- [translation_service/app/utils/script_detect.py](../app/utils/script_detect.py)
- [translation_service/app/pipeline/language_router.py](../app/pipeline/language_router.py)
- [translation_service/app/pipeline/translator_pipeline.py](../app/pipeline/translator_pipeline.py)
- [translation_service/app/models/gemma_model.py](../app/models/gemma_model.py)
- [translation_service/app/models/googletrans_model.py](../app/models/googletrans_model.py)
- [translation_service/app/models/indictrans2_model.py](../app/models/indictrans2_model.py)
- [translation_service/app/models/qwen_model.py](../app/models/qwen_model.py)
- [translation_service/configs/language_models.yaml](../configs/language_models.yaml)

---

## Root cause

The pipeline is doing this in sequence:

1. detect script type and language candidate
2. route to a model chain
3. send the result to model-specific translation logic
4. store the detected language as returned by that layer

Different layers are not sharing one canonical language vocabulary.

That is why the aggregate log ends up with multiple labels for one real language.

---

## Expected normalization strategy

We should normalize all language labels into one canonical code before using them for:

- logs
- stats
- route selection
- cache keys
- API responses
- downstream model decisions

Recommended canonical form:

- ISO 639-1 where available: `en`, `hi`, `bn`, `ur`, `pa`, etc.
- special mixed bucket: `mix`
- unknown bucket: `und`
- keep aliases resolved via a single alias map

---

## Canonical mapping for common observed labels

The normalization should treat these as the same language:

| Canonical code | Normalize from |
|---|---|
| `am` | `am`, `amharic`, `amharistic` |
| `ar` | `ar`, `arabic` |
| `as` | `as`, `assamese` |
| `bn` | `bn`, `bengal`, `bengali` |
| `bg` | `bg` |
| `my` | `my`, `mya`, `burmese` |
| `zh` | `zh`, `chinese`, `zh-cn`, `zh-tw` |
| `cs` | `cs` |
| `de` | `de`, `german` |
| `el` | `el`, `greek` |
| `en` | `en`, `eng`, `english` |
| `es` | `es`, `spa`, `spanish` |
| `fa` | `fa` |
| `fr` | `fr`, `french` |
| `ka` | `georgian` |
| `he` | `he`, `hebrew` |
| `hi` | `hi`, `hin`, `hindi` |
| `id` | `id`, `indonesian` |
| `it` | `it`, `italian` |
| `ja` | `ja`, `japanese` |
| `kn` | `kn`, `kannada` |
| `ko` | `ko` |
| `ml` | `ml`, `malayalam` |
| `mr` | `mr`, `marathi` |
| `ne` | `ne`, `new` |
| `nl` | `nl` |
| `or` | `or`, `odia` |
| `pa` | `pa`, `punjabi` |
| `ps` | `ps`, `pashto` |
| `pt` | `pt`, `portuguese` |
| `ru` | `ru`, `rus`, `russian` |
| `sa` | `sa` |
| `si` | `si`, `sinhala` |
| `sd` | `sd`, `sindhi` |
| `sv` | `sv` |
| `sw` | `sw`, `swahili` |
| `ta` | `ta`, `tamil` |
| `te` | `te`, `telugu` |
| `th` | `th`, `thai` |
| `tl` | `tl`, `tagalog` |
| `tr` | `tr`, `turkish` |
| `uk` | `uk` |
| `ur` | `ur`, `urdu` |
| `dv` | `dv`, `dh`, `dhiv`, `dhivehi`, `maldivian` |
| `gu` | `gu`, `gujarati` |
| `mix` | `mixed`, `multilingual`, `hinglish`, `hinglish-burmese mixed` |
| `und` | `und`, `unknown`, `unidentified`, empty, null-like |
| `mis` | `mis` |

---

## Model logic and source language flow

### 1. Which model gets which source language?

| Model | Source language it receives | Rule |
|---|---|---|
| Gemma | user-provided source language or the detected language from routing | Gemma can handle `auto` internally and does its own detection in its prompt layer |
| Googletrans | the request source language passed down if route allows it | blocked for Latin/romanized/mixed-script routes |
| IndicTrans2 | a resolved known language code, never raw `auto` | forced to use the resolved detected language in the pipeline |
| Qwen | the selected chain’s source language value | no special override logic in this repo |

The actual routing behavior comes from:

- [translation_service/app/pipeline/translator_pipeline.py](../app/pipeline/translator_pipeline.py)
- [translation_service/app/pipeline/language_router.py](../app/pipeline/language_router.py)

The key rule is:

- if `source_lang != "auto"`, use that
- if `source_lang == "auto"`, detect the language and choose a route
- for IndicTrans2 specifically, the pipeline resolves the detected language before sending it to the model

---

### 2. Native-script behavior

| Input kind | Detector logic | Model behavior |
|---|---|---|
| Native script | [translation_service/app/utils/script_detect.py](../app/utils/script_detect.py) checks Unicode script blocks and uses langid + dominant script mapping | Native-script text is allowed to go to Googletrans if the route says so |
| Gemma | strong for native-script translation and fallback | used broadly for many languages |
| IndicTrans2 | valid for supported Indic source languages | only for `target_lang == "en"` |
| Googletrans | allowed | used only for native-script high-confidence cases |
| Qwen | used in some language chains | not the primary detection pathway |

---

### 3. Romanized / transliterated behavior

| Input kind | Detector logic | Model behavior |
|---|---|---|
| Romanized | [translation_service/app/utils/script_detect.py](../app/utils/script_detect.py) checks romanized Indic keyword lexicons | Googletrans is blocked |
| Gemma | preferred | explicitly used for romanized/mixed-script text |
| Qwen | supports transliterated reconstruction in prompt design | can be selected by chain |
| Googletrans | blocked | not used for Latin-like inputs |
| IndicTrans2 | not appropriate | expects a native Indic language, not romanized input |

---

### 4. Mixed-script behavior

| Input kind | Detector logic | Model behavior |
|---|---|---|
| Mixed script | app-level route treats it as Latin-like / mixed, not a valid Googletrans candidate | Gemma is preferred |
| Gemma | best fit | explicitly designed for mixed-script handling in the reference Gemma engine |
| Qwen | can be used if chain selects it | not the main design choice |
| Googletrans | blocked | not allowed for mixed-script or romanized text |
| IndicTrans2 | not appropriate | not designed for mixed inputs |

---

## IndicTrans2-specific logic

The IndicTrans2 microservice in [translation_service/app/models/indictrans2_model.py](../app/models/indictrans2_model.py) explicitly expects:

- `target_lang == "en"`
- a known source language code such as `hi`, `bn`, `as`, `ne`, `pa`, `ml`, `ur`
- not raw `auto`

It returns:

- `translated_text`
- `detected_language=source_lang`

That means normalization must happen before calling IndicTrans2, not just after the response.

The supported Indic route list is defined in [translation_service/configs/language_models.yaml](../configs/language_models.yaml).

---

## Recommended implementation order

1. Add a central alias map in [translation_service/app/utils/lang_codes.py](../app/utils/lang_codes.py)
2. Add `normalize_language_code(raw)`
3. Normalization before model dispatch
4. Normalization before logging and stats aggregation
5. Keep raw values only as debug metadata if needed
6. Add tests for alias reductions such as:
   - `en`, `eng`, `english` -> `en`
   - `bn`, `bengal`, `bengali` -> `bn`
   - `hi`, `hin`, `hindi` -> `hi`
   - `my`, `mya`, `burmese` -> `my`
   - `mixed`, `multilingual`, `hinglish` -> `mix`
   - `unknown`, `und`, empty -> `und`

---

## Bottom line

The duplicates you are seeing are the expected result of unnormalized backend outputs from different models and detectors.

The right fix is not to change translation logic itself; it is to canonicalize the language label once at the service boundary.

Once that is done, all the counts in the log should consolidate into a single stable code per language instead of multiple labels for the same language.
