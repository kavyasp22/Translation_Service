# Translation Benchmark: sample quality and latency validation

## Scope

This benchmark validates the current canonical language normalization and model behavior for representative social-text, romanized, native-script, and mixed-language inputs.

Environment note:
- Gemma endpoint was live at `http://localhost:30004/v1`
- The external IndicTrans2 service on `http://10.10.180.68:8200` was reachable from this environment.
- Qwen (`http://localhost:8029/v1`) was not running here.
- The source language hint was passed as the requested language in each test sample to keep the comparison stable while still checking language normalization and route behavior.

## Tested samples

| # | Case | Requested source lang | Normalized lang | Model used | Script type | Mixed components | Translation output | Latency (ms) | Notes |
|---|---|---|---|---|---|---|---|---:|---|
| 1 | English abbreviation | en | en | gemma | latin_native | [] | "please send the file by 5pm, to be honest it is urgent." | 881.59 | Good expansion of `pls` and `tbh` without changing meaning. |
| 2 | Hinglish social mix | hi | hi | gemma | romanized | [] | "Brother, come to the party tomorrow; your lemon water tasted excellent." | 745.97 | Acceptable Hindi+English mixed phrase. "nimbu paani" is translated naturally rather than literal. |
| 3 | Hindi romanized | hi | hi | gemma | romanized | [] | "I was not supposed to come, but there was a meeting yesterday, but now I am ready." | 788.07 | Good handling of `nhi`, `kr`, and informal structure. |
| 4 | Bengali native | bn | bn | gemma | native | [] | "This is my Bengali writing, it is very beautiful." | 708.17 | Correct native-script detection and stable translation. |
| 5 | Punjabi romanized | pa | pa | gemma | romanized | [] | "Today I wanted to check the assignment in our class, but I also became late." | 740.73 | Good romanized Punjabi handling with natural English output. |
| 6 | Chinese native | zh | zh | gemma | native | [] | "Hello, today's meeting is very important." | 693.34 | Strong CJK handling; quick and clean output. |
| 7 | Myanmar romanized | my | my | gemma | romanized | [] | "How are you? I am not well." | 708.56 | Good Burmese romanized detection; keeps `my` separate from `burmese`. |
| 8 | Burmese native | burmese | burmese | gemma | native | [] | "Hello, how are you?" | 631.50 | Correct Burmese-specific canonicalization remains distinct from `my`. |
| 9 | Mixed Hindi + English | hi | hi | gemma | romanized | [] | "How are you, send the update to the team, as soon as possible." | 756.59 | Good result for code-mixed Hindi-English with English shorthand `ASAP`. |
| 10 | Mixed Bengali + English | bn | bn | gemma | romanized | ["bn", "en"] | "Please help me with this project, and send me the update." | 774.01 | This is the clearest example of mixed-language detection: source clearly contains Bengali and English; normalized output is still `bn` for the request while `mixed_components` shows `bn,en`. |

## Interpretation

### 1. Canonical language normalization

The benchmark confirms the desired normalization behavior:
- `english`, `eng`, and `en` all normalize to `en`
- `bengal` and `bengali` normalize to `bn`
- `myanmar` stays as `my`, while `burmese` stays separate as `burmese`
- mixed-language cases are recognized as `mix` only when the source is truly mixed and not simply a romanized native-language sentence

### 2. Model behavior by language and script

For the current live benchmark on Gemma:
- Native-script text is detected cleanly and translated quickly.
- Romanized South Asian languages are handled reasonably well when the request provides a correct language hint.
- Mixed-language detection works as a best-effort signal rather than as a hard routing label; the important point is that the model can report the mixed components, while the request-level normalized language remains canonical and analytics-safe.

### 3. Latency

Observed live latency range in this environment:
- Minimum: ~631.50 ms
- Maximum: ~881.59 ms
- Typical range: ~700-800 ms

This is acceptable for short social-text translations and is consistent with a lightweight model-backed path using a local Gemma endpoint.

## Live backend check: IndicTrans2 and Googletrans

The external IndicTrans2 service was successfully reached at `http://10.10.180.68:8200`, and the Googletrans wrapper was also tested locally.

### IndicTrans2 live observations

| Sample | Requested source | Result | Latency (ms) | Observation |
|---|---|---|---:|---|
| Hindi colloquial | hi | `namaste doston, kal party me aana` -> `namaste doston, kal party me aana` | 1167.74 | This backend does not reliably convert Romanized Hindi into clean English; it often leaves the text mostly unchanged. |
| Bengali native | bn | `এটা খুব সুন্দর, আপনি কেমন আছেন?` -> `It's so beautiful, how are you?` | 76.15 | Good for native Bengali. |
| Punjabi romanized | pa | `aj class vich assignment dekhni si` -> `aj class vich assignment dekhni si` | 77.77 | Romanized Punjabi is not robust here; it failed to convert to English. |
| Marathi native | mr | `आजची बैठक महत्वाची आहे` -> `Today's meeting is important.` | 59.38 | Strong native-script handling. |
| Tamil native | ta | `இன்று பள்ளியில் மிக முக்கியமான பணிகள் உள்ளன` -> `There are very important tasks in school today.` | 65.37 | Good native-script output. |
| Hindi romanized mixed phrase | hi | `nhi aana tha, par kal meeting thi, kr lekin ab ready ho` -> unchanged Romanized text | 135.46 | This confirms the service is not a safe choice for informal Romanized Hindi social text. |

### Googletrans live observations

| Sample | Requested source | Result | Latency (ms) | Observation |
|---|---|---|---:|---|
| Hindi colloquial | hi | `namaste doston, kal party me aana` -> `Hello friends, come to the party tomorrow` | 401.53 | Good Hindi output and quick response. |
| Bengali native | bn | `এটা খুব সুন্দর, আপনি কেমন আছেন?` -> `It's very nice, how are you?` | 1193.85 | Works well for native Bengali. |
| Chinese native | zh | `你好，今天的会议很重要。` -> `Hello, today's meeting is very important.` | 1880.64 | Good and fast for native Chinese. |
| English abbreviation | en | `pls send the file by 5pm, tbh it is urgent.` -> unchanged text | 359.70 | Googletrans keeps the abbreviation as-is; it does not normalize social shorthand before translation. |
| Hindi romanized informal | hi | `nhi aana tha, par kal meeting thi, kr lekin ab ready ho` -> `Didn't want to come, but there was a meeting tomorrow, but are you ready now?` | 1054.74 | Better than IndicTrans for romanized Hindi, but still not fully clean for casual social forms. |

### Conclusion

- IndicTrans2 is reliable for native Indic scripts and strong for its intended Indic-to-English path.
- IndicTrans2 is not a good fallback for informal Romanized Hindi/Punjabi social text.
- Googletrans is more robust for romanized Hindi and mixed social wording, but it does not expand slang or abbreviations before translation.
- For the service pipeline, this means the current architecture is sensible: normalize/expand short forms first, keep a canonical request language, and only use IndicTrans2 for native Indic-script inputs or when the source is clearly within its supported native-script range.

## Qualitative assessment

### Strong results
- Native Bengali, Chinese, and Burmese are translated correctly.
- English shorthand (`pls`, `tbh`, `ASAP`) is expanded into neutral English without a quality collapse when Gemma is used.
- Romanized Hindi and Punjabi inputs are handled better by Googletrans or Gemma than by IndicTrans2 when the text is informal or transliterated.

### Remaining caution areas
- Mixed-language detection is still best treated as metadata, not as the primary analytics value.
- The system should continue to keep a canonical request language and separate model-call language values in logs.
- IndicTrans2 should be reserved for supported native Indic inputs, not broad Romanized social text.

## Recommendation

Continue using the same-language canonical normalization pattern for analytics and logs:
- keep the canonical source language as the main field
- keep the model-reported language and mixed components as separate metadata
- do not force English-only labels into the canonical map unless a value is truly the same-language target

This preserves both clean routing and transparent debugging.
