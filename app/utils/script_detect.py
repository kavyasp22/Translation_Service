"""
Decides two things before any model is called:
  1. script_type  -> "native" (Devanagari, Tamil, Arabic, etc.) or "latin"
  2. confidence    -> how sure we are about the detected language (via langid)

Googletrans has been removed from the project, so Gemma is now the only
model in the generic (not-in-yaml-table) fallback path - there's no second
engine left to choose between. script_type/confidence/route_reason are still
computed and returned because they're useful metadata (surfaced in the API
response, and still meaningful for language-specific chains in
configs/language_models.yaml, e.g. promoting Gemma to the front of a chain
for romanized text), they just no longer affect which model runs when a
language isn't in that table.
"""
from langid.langid import LanguageIdentifier, model as _langid_model

from app.utils.lang_codes import normalize_language_code

# norm_probs=True gives a 0-1 confidence instead of an unbounded raw log-prob
# that scales with text length and isn't comparable across inputs of
# different sizes - the raw score made a 40-char English sentence look
# "more confident" than a clearly-correct Hindi detection.
_identifier = LanguageIdentifier.from_modelstring(_langid_model, norm_probs=True)

# Unicode block ranges for common native scripts (expanded for all supported Indic languages).
_NATIVE_SCRIPT_RANGES = [
    (0x0900, 0x097F),  # Devanagari (Hindi, Marathi, Sanskrit, Nepali, Konkani, Bodo, Dogri, Maithili)
    (0x0980, 0x09FF),  # Bengali/Assamese (Bengali, Assamese, Manipuri)
    (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Odia
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic supplement (Urdu, Kashmiri, Pashto, Balochi)
    (0x0780, 0x07BF),  # Thaana (Divehi)
    (0x1C50, 0x1C7F),  # Ol Chiki (Santali)
    (0xABC0, 0xABFF),  # Meetei Mayek (Manipuri)
    (0xAAE0, 0xAAFF),  # Meetei Mayek Extension
    (0x1000, 0x109F),  # Myanmar (Burmese)
    (0xA9E0, 0xA9FF),  # Myanmar Extended-B
    (0xAA60, 0xAA7F),  # Myanmar Extended-A
    (0x4E00, 0x9FFF),  # CJK unified (Chinese)
    (0x3040, 0x30FF),  # Hiragana/Katakana (Japanese)
    (0xAC00, 0xD7A3),  # Hangul (Korean)
    (0x0400, 0x04FF),  # Cyrillic
]

# Primary script code mappings to fallback language codes when langid fails
_SCRIPT_PRIMARY_LANG = {
    (0x0900, 0x097F): "hi",
    (0x0980, 0x09FF): "bn",
    (0x0A00, 0x0A7F): "pa",
    (0x0A80, 0x0AFF): "gu",
    (0x0B00, 0x0B7F): "or",
    (0x0B80, 0x0BFF): "ta",
    (0x0C00, 0x0C7F): "te",
    (0x0C80, 0x0CFF): "kn",
    (0x0D00, 0x0D7F): "ml",
    (0x0600, 0x06FF): "ur",
    (0x1C50, 0x1C7F): "sat",
    (0xABC0, 0xABFF): "mni",
    (0x1000, 0x109F): "my",
}

# Distinctive function word lexicons for Romanized (transliterated) Indic detection
_ROMANIZED_INDIC_LEXICONS = {
    "hi": {"kaise", "hain", "kya", "aap", "theek", "hoon", "mujhae", "mera", "nahin", "hoga", "chahiye", "karne", "raha", "bhai", "shukriya"},
    "bn": {"kemon", "acho", "khobor", "dada", "tumi", "apni", "amader", "korechi", "bhalo", "dhonnobad"},
    "ta": {"vanakkam", "eppadi", "irukkinga", "nalla", "illai", "pannunga", "nandri", "theriyum"},
    "te": {"ela", "unnaru", "bavunnara", "nenu", "enti", "cheyali", "leka", "dhanayavadalu"},
    "ps": {"pashto", "pukhto", "zama", "khwa", "sta", "dah", "da", "de", "khe", "wakh", "kha", "ghwa", "sanga", "khpal", "sara", "khor"},
    "bal": {"balochi", "baloch", "mehnan", "khi", "ham", "zabaan", "zaban", "peh", "haq", "surr", "buzurg", "khan", "shar", "aagha", "sar"},
    "dv": {"dhivehi", "divehi", "hithu", "aharen", "vanee", "kohe", "dheyn", "faharu", "faharu", "mira", "beyan", "bahaa", "kudhi"},
}

LOW_CONFIDENCE_THRESHOLD = 0.5


def _is_native_char(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in _NATIVE_SCRIPT_RANGES)


def _get_dominant_native_script_lang(text: str) -> str | None:
    counts = {}
    for c in text:
        cp = ord(c)
        for (start, end), lang in _SCRIPT_PRIMARY_LANG.items():
            if start <= cp <= end:
                counts[lang] = counts.get(lang, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return None


def detect_script_type(text: str) -> str:
    """Returns 'native' if text contains a meaningful share of native-script characters, else 'latin'."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "latin"
    native_count = sum(1 for c in letters if _is_native_char(c))
    ratio = native_count / len(letters)
    return "native" if ratio > 0.3 else "latin"


def detect_romanized_indic(text: str) -> tuple[str, float] | None:
    """Detects transliterated Indic text (e.g. Hinglish, Tanglish) using keyword heuristics."""
    lowered = text.lower()
    words = set(lowered.split())

    explicit_lang = {
        "ps": {"pashto", "pukhto", "zama", "khpal", "khwa", "ghwa", "wakh"},
        "bal": {"balochi", "baloch", "zaban", "zabaan", "phundi", "agha", "khan"},
        "dv": {"dhivehi", "divehi", "faharu", "hithu", "vanee", "kudhi"},
    }
    for lang, lexicon in explicit_lang.items():
        if any(token in lowered for token in lexicon):
            return lang, 0.9

    for lang, lexicon in _ROMANIZED_INDIC_LEXICONS.items():
        matched = words.intersection(lexicon)
        if len(matched) >= 1:
            return lang, 0.85
    return None


def detect_language(text: str) -> tuple[str, float]:
    """Returns (lang_code, confidence) with script-aware heuristics and langid fallback."""
    script_type = detect_script_type(text)
    dominant_script_lang = _get_dominant_native_script_lang(text)

    # Special disambiguation for Assamese ('as') vs Bengali ('bn') in script block (0x0980-0x09FF)
    if any("\u0980" <= c <= "\u09ff" for c in text):
        assamese_chars = {"\u09f0", "\u09f1"}  # Unique Assamese letters: Ra (ৰ) and Wa (ৱ)
        assamese_words = {"মই", "আছোঁ", "আপুনি", "কেতিয়া", "আহিব", "হ’ব", "নহয়", "অসমীয়া", "কৰা"}
        words_in_text = set(text.split())
        if any(c in assamese_chars for c in text) or words_in_text.intersection(assamese_words):
            return "as", 0.95

    # Check langid prediction
    lang_code, confidence = _identifier.classify(text)
    lang_code = normalize_language_code(lang_code)

    # If text is native script and has a clear script mapping, prioritize script mapping over langid misclassifications
    if script_type == "native" and dominant_script_lang:
        dominant_script_lang = normalize_language_code(dominant_script_lang)
        if lang_code == "en" or confidence < LOW_CONFIDENCE_THRESHOLD or dominant_script_lang in {"sat", "mni", "pa", "gu", "or", "ta", "te", "kn", "ml", "my"}:
            return dominant_script_lang, max(confidence, 0.85)

    # If text is latin script, check for romanized Indic keywords
    if script_type == "latin":
        romanized_match = detect_romanized_indic(text)
        if romanized_match:
            return romanized_match

    return lang_code, confidence


def classify_routing(text: str) -> dict:
    """Single entry point the pipeline calls. Returns routing parameters."""
    script_type = detect_script_type(text)
    romanized_match = detect_romanized_indic(text) if script_type == "latin" else None

    if romanized_match:
        lang_code, confidence = romanized_match
        lang_code = normalize_language_code(lang_code)
        reason = f"romanized_indic_keyword_match:{lang_code}"
    else:
        lang_code, confidence = detect_language(text)
        lang_code = normalize_language_code(lang_code)
        if script_type == "native":
            reason = (
                "native_script_low_confidence"
                if confidence < LOW_CONFIDENCE_THRESHOLD
                else "native_script_high_confidence"
            )
        else:
            reason = "latin_english" if lang_code == "en" and confidence > LOW_CONFIDENCE_THRESHOLD else "romanized_or_mixed"

    return {
        "script_type": script_type,
        "detected_lang": lang_code,
        "confidence": confidence,
        "route_reason": reason,
    }
