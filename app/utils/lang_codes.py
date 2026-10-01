"""
Different backends speak different language-code dialects. This is the one
place that translates between them, keyed by our internal ISO-639-1-ish code
(what langid.py and the API request use, e.g. 'hi', 'bn', 'mni').
"""

import re

# IndicTrans2 wants FLORES-200 style codes like "hin_Deva", "eng_Latn".
# Only languages the indic-en-1B checkpoint actually supports are listed;
# extend if you load the en-indic or indic-indic checkpoints too.
ISO_TO_FLORES = {
    "en": "eng_Latn", "hi": "hin_Deva", "bn": "ben_Beng", "as": "asm_Beng",
    "pa": "pan_Guru", "ne": "npi_Deva", "ml": "mal_Mlym", "ur": "urd_Arab",
    "gu": "guj_Gujr", "kn": "kan_Knda", "mr": "mar_Deva", "or": "ory_Orya",
    "ta": "tam_Taml", "te": "tel_Telu",
    # Manipuri (Meitei script) - IndicTrans2 uses Bengali-script code for this
    "mni": "mni_Beng",
}

# Canonical alias map: raw backend labels -> the single language code we want in
# logs, stats, and routing decisions. This collapses values like "english",
# "eng", "en" into one canonical `en` bucket.
ALIASES_TO_CANONICAL = {
    "af": "af", "afrikaans": "af",
    "am": "am", "amharic": "am", "amharistic": "am",
    "ar": "ar", "arab": "ar", "arabic": "ar",
    "as": "as", "assamese": "as", "asamiya": "as", "asm": "as",
    "az": "az", "azeri": "az", "azerbaijani": "az",
    "bal": "bal", "balochi": "bal", "baluchi": "bal", "baloch": "bal",
    "be": "be", "belarusian": "be",
    "bg": "bg", "bulgarian": "bg",
    "bn": "bn", "ben": "bn", "bengal": "bn", "bengali": "bn",
    "bs": "bs", "bosnian": "bs",
    "ca": "ca", "catalan": "ca",
    "cs": "cs", "czech": "cs",
    "da": "da", "danish": "da",
    "de": "de", "german": "de", "deutsch": "de",
    "dv": "dv", "dh": "dv", "dhiv": "dv", "dhivehi": "dv", "divehi": "dv", "maldivian": "dv",
    "el": "el", "greek": "el",
    "en": "en", "eng": "en", "english": "en",
    "es": "es", "spa": "es", "spanish": "es",
    "et": "et", "estonian": "et",
    "fa": "fa", "farsi": "fa", "persian": "fa",
    "fi": "fi", "finnish": "fi",
    "fr": "fr", "french": "fr",
    "ga": "ga", "irish": "ga",
    "georgian": "ka", "ka": "ka",
    "gom": "gom", "konkani": "gom",
    "gu": "gu", "guj": "gu", "gujarati": "gu",
    "ha": "ha", "hausa": "ha",
    "he": "he", "iw": "he", "hebrew": "he",
    "hi": "hi", "hin": "hi", "hindi": "hi",
    "hr": "hr", "croatian": "hr",
    "hu": "hu", "hungarian": "hu",
    "id": "id", "ind": "id", "indonesian": "id",
    "ig": "ig", "igbo": "ig",
    "it": "it", "italian": "it", "it-my": "it",
    "ja": "ja", "japanese": "ja",
    "ka": "ka", "georgian": "ka",
    "kannada": "kn", "kn": "kn",
    "khmer": "km", "km": "km",
    "kinyarwanda": "rw", "rw": "rw",
    "ko": "ko", "korean": "ko",
    "lao": "lo", "lo": "lo",
    "lt": "lt", "lithuanian": "lt",
    "lv": "lv", "latvian": "lv",
    "ml": "ml", "mal": "ml", "malayalam": "ml",
    "mn": "mn", "mongolian": "mn",
    "mr": "mr", "marathi": "mr", "marwari": "mr",
    "ms": "ms", "malay": "ms",
    "my": "my", "myanmar": "my", "myan": "my", "myanmar-language": "my", "burmese": "burmese", "mya": "burmese", "burmese-language": "burmese",
    "mni": "mni", "manipuri": "mni", "meitei": "mni",
    "ne": "ne", "new": "ne", "nepali": "ne", "newari": "ne",
    "nl": "nl", "dutch": "nl",
    "no": "no", "norwegian": "no",
    "nso": "nso", "northern-sotho": "nso", "northern sotho": "nso",
    "or": "or", "odia": "or", "oriya": "or",
    "pa": "pa", "punjabi": "pa", "panjabi": "pa", "shahmukhi": "pa",
    "pl": "pl", "polish": "pl",
    "ps": "ps", "pashto": "ps", "pushto": "ps",
    "pt": "pt", "portuguese": "pt",
    "ro": "ro", "romanian": "ro",
    "ru": "ru", "rus": "ru", "russian": "ru",
    "sa": "sa", "sanskrit": "sa",
    "sat": "sat", "santali": "sat",
    "sd": "sd", "sindhi": "sd",
    "shona": "sn", "sn": "sn",
    "si": "si", "sinhala": "si", "sinhalese": "si",
    "sk": "sk", "slovak": "sk",
    "sl": "sl", "slovene": "sl", "slovenian": "sl",
    "so": "so", "somali": "so",
    "sq": "sq", "albanian": "sq",
    "sr": "sr", "serbian": "sr",
    "sv": "sv", "swedish": "sv",
    "sw": "sw", "swahili": "sw",
    "ta": "ta", "tamil": "ta",
    "te": "te", "telugu": "te",
    "th": "th", "thai": "th",
    "tl": "tl", "tagalog": "tl", "filipino": "tl",
    "tr": "tr", "turkish": "tr",
    "tcy": "tcy", "kodava": "tcy",
    "uk": "uk", "ukrainian": "uk",
    "ur": "ur", "urd": "ur", "urdu": "ur",
    "vi": "vi", "vietnamese": "vi",
    "yo": "yo", "yoruba": "yo",
    "zomi": "zomi",
    "zh": "zh", "zho": "zh", "chinese": "zh", "zh-cn": "zh", "zh-tw": "zh", "zh-hant": "zh", "zh-hans": "zh",
    "zu": "zu", "zulu": "zu",
    "mixed": "mix", "multilingual": "mix", "hinglish": "mix", "hinglish-burmese-mixed": "mix", "hinglish-burmese mixed": "mix",
    "code-mixed": "mix", "latin-mixed": "mix", "romanized": "mix", "romanized-mixed": "mix", "romanized/mixed": "mix",
    "mix": "mix",
    "und": "und", "unknown": "und", "unidentified": "und",
    "latin": "und",
    "mis": "mis",
    "creole": "mix", "haitian creole": "mix",
    "bengal": "bn",
    "hindi": "hi",
    "english": "en",
    "arabic": "ar",
    "newari": "ne",
    "maldivian": "dv",
    "telugu": "te",
    "burmese-mixed": "mix",
    "my-en": "mix",
    "zh-my": "mix",
    "itmy": "it",
}


def normalize_language_code(raw: str | None) -> str:
    """Normalize backend-specific language labels into one canonical code."""
    if raw is None:
        return "und"

    value = str(raw).strip().lower()
    if not value:
        return "und"

    # Collapse separators and stray punctuation so things like "zh_cn" and
    # "zh-cn" both become the same canonical code.
    value = value.replace("_", "-")
    value = value.replace("/", "-")
    value = value.replace("\\", "-")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9\-]", "", value)

    if not value:
        return "und"

    # Direct exact alias mapping takes precedence.
    if value in ALIASES_TO_CANONICAL:
        return ALIASES_TO_CANONICAL[value]

    # Common region variants like "zh-cn" -> "zh" and "en-us" -> "en".
    base = value.split("-")[0]
    if base in ALIASES_TO_CANONICAL:
        return ALIASES_TO_CANONICAL[base]

    return "und"


def to_flores_code(iso_code: str) -> str:
    if iso_code not in ISO_TO_FLORES:
        raise KeyError(f"No FLORES mapping for '{iso_code}' - IndicTrans2 may not support it")
    return ISO_TO_FLORES[iso_code]
