# Multilingual Shortcut Normalization Plan

## Recommendation

Use a language-grouped map for readability, but keep the normalization target in the same language as the original shortcut. Do not treat English meaning as the primary normalization target.

Recommended structure:

```python
MULTILINGUAL_SHORTCUT_MAP = {
    "hi": {
        "kya": {
            "canonical": "kya",
            "native_form": "क्या",
            "english_meaning": "what",
        },
        "nhi": {
            "canonical": "nahin",
            "native_form": "नहीं",
            "english_meaning": "no / not",
        },
        "kr": {
            "canonical": "kar",
            "native_form": "कर",
            "english_meaning": "do",
        },
        "thik": {
            "canonical": "theek",
            "native_form": "ठीक",
            "english_meaning": "okay / correct",
        },
    },
    "bn": {
        "accha": {
            "canonical": "accha",
            "native_form": "আচ্ছা",
            "english_meaning": "okay",
        }
    }
}
```

## Why this is better

1. It keeps normalization and translation separate.
   - `canonical` is the value used for normalized text analytics.
   - `english_meaning` is metadata, not the canonical target.

2. It supports real language-aware logic.
   - We can normalize `nhi` -> `nahin` in Hindi.
   - We can normalize `accha` -> `accha` in Bengali.
   - We can log the English interpretation separately for analytics or debugging.

3. It makes testing easier.
   - Unit tests can verify a shortcut resolves to the correct same-language form.
   - English mapping remains optional metadata.

4. It prevents accidental English-only normalization.
   - The system does not lose language intent by collapsing everything into English.

---

## Recommended runtime behavior

Use a two-stage flow:

1. Normalize shortcut to canonical same-language form
2. Optionally attach English meaning for logging or metadata display

Pseudo-flow:

```python
def normalize_multilingual_shortcut(lang: str, text: str):
    lang_map = MULTILINGUAL_SHORTCUT_MAP.get(lang, {})
    entry = lang_map.get(text.lower())
    if not entry:
        return text
    return entry["canonical"]
```

Then separately:

```python
def get_shortcut_metadata(lang: str, text: str):
    entry = MULTILINGUAL_SHORTCUT_MAP.get(lang, {}).get(text.lower())
    if not entry:
        return None
    return {
        "canonical": entry["canonical"],
        "native_form": entry["native_form"],
        "english_meaning": entry["english_meaning"],
    }
```

---

## Recommended canonicalization rule

For multilingual shortcuts:

- primary target = same-language full form
- secondary metadata = English meaning
- not recommended = English-only value as the main canonical field

Examples:

- `nhi` -> `nahin` (not `no`)
- `kr` -> `kar` (not `do`)
- `thik` -> `theek` (not `okay`)
- `accha` -> `accha` (not `okay`)
- `xie xie` -> `xie xie` or `谢谢` depending on the exact canonical choice you want to enforce

This rule keeps the system aligned with the language being normalized, while still allowing English metadata for reporting.

---

## Implementation plan

1. Create a `MULTILINGUAL_SHORTCUT_MAP` grouped by language code.
2. Each shortcut entry should contain:
   - `canonical`
   - `native_form`
   - `english_meaning`
3. Add a helper such as `normalize_multilingual_shortcut(lang, token)`.
4. Add a helper such as `get_shortcut_metadata(lang, token)`.
5. Keep the English-only abbreviation map separate from the multilingual map.
6. Only apply multilingual normalization when the language is known or the text is clearly in that language family.
7. Add tests for the key cases:
   - `hi/nhi -> nahin`
   - `hi/kr -> kar`
   - `hi/thik -> theek`
   - `bn/accha -> accha`
   - `zh/xie xie -> xie xie` or `谢谢` depending on canonical target choice

---

## Suggested scope for the first pass

Keep the first pass conservative and only include very common social shorthand, for example:

### Hindi / Hinglish
- `kya`, `kr`, `kro`, `nhi`, `ha`, `haan`, `bs`, `bss`, `thik`, `sahi`, `abhi`, `chalo`, `jldi`

### Bengali
- `ki`, `na`, `accha`, `bhalo`, `kaaj`, `kemon`

### Punjabi
- `hun`, `nahi`, `shukriya`, `sahi`

### Assamese
- `hoi`, `kemon`, `bhal`

### Chinese
- `xie xie`, `ni hao`, `hao`

This keeps the map useful, readable, and low-risk for model behavior.

---

## Final recommendation

If the goal is clean normalization, this is the recommended design:

- same-language canonical value is the primary field
- English meaning is metadata
- the map stays grouped by language for inspection and maintenance
- the model layer should not depend on English meaning for routing or normalization decisions

This is clearer, more testable, and more maintainable than using English as the only canonical value.
