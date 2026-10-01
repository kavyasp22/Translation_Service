"""Shared text cleanup for common English short forms in mixed-language content.

This is intentionally conservative: it only expands a small allowlist of very
common social-media abbreviations that are low-risk for translation quality.
The goal is not to rewrite arbitrary English text, but to reduce obvious short
forms before the model sees the input.
"""

import re

# Conservative allowlist: expand only short forms that are common in social text
# and low-risk to rewrite without changing the larger meaning.
# Recommended approach: keep the English abbreviations and the multilingual chat
# shortcuts in separate dictionaries. This keeps model behavior easier to reason
# about and avoids one giant flat map where English, Hinglish, and regional terms
# blur together.
# Common texting / chat shortcuts
_ABBREVIATION_MAP = {
    "pls": "please",
    "plz": "please",
    "msg": "message",
    "msgs": "messages",
    "bcoz": "because",
    "bcz": "because",
    "bcos": "because",
    "coz": "because",
    "cuz": "because",
    "fyi": "for your information",
    "asap": "as soon as possible",
    "u": "you",
    "ur": "you are",
    "r": "are",
    "b4": "before",
    "gonna": "going to",
    "gotta": "have to",
    "wanna": "want to",
    # Gen Z / meme slang
    "fr": "for real",
    "srsly": "seriously",
    "nah": "no",
    "yea": "yes",
    "ye": "yes",
    "fam": "family / close friend",
    "slay": "do really well",
    "sus": "suspicious",
    "cap": "lie",
    "bet": "okay / agreed",
    "rizz": "charm",
    "vibe": "mood",
    "cringe": "awkward",
    "skibidi": "nonsense",
    "gyatt": "wow",
    "sigma": "strong independent person",
    "mewing": "face posture",
    "mid": "average or boring",
    "npc": "unoriginal person",
    "based": "confident and unapologetic",
    "cringe": "embarrassing",
    "slay": "did very well",
    "sus": "suspicious",
    "bussin": "very good",
    "cap": "lie",
    "no cap": "truth",
    "bet": "okay",
    "fire": "awesome",
    "lit": "exciting",
    "drip": "stylish outfit",
    "flex": "show off",
    "lowkey": "quietly",
    "highkey": "strongly",
    "ghosting": "sudden ignoring",
    "shook": "surprised",
    "vibe": "feeling or mood",
    "main character": "confident person",
    "side quest": "small task",
    "touch grass": "go outside",
    "goofy": "foolish",
    "delulu": "delusional",
    "stan": "big fan",
    "iykyk": "if you know you know",
    "simp": "overly devoted",
    "glow up": "big improvement",
    "clapback": "smart comeback",
    "snack": "attractive person",
    "tea": "gossip",
    "spill the tea": "share gossip",
    "goated": "greatest ever",
    "goat": "greatest of all time",
    "af": "very",
    "pov": "point of view",
    "real one": "loyal person",
    "boujee": "fancy",
    "cheugy": "outdated trend",
    "fit": "outfit",
    "say less": "i understand",
    "hits different": "feels special",
    "hard": "very impressive",
    "soft launch": "subtle announcement",
    "hard launch": "public reveal",
    "era": "life phase",
    "canon event": "important moment",
    "caught in 4k": "exposed clearly",
    "smth": "something",
    # Social / online shorthand and check-ins
    "tysm": "thank you so much",
    "yw": "you are welcome",
    "rs": "really sorry",
    "hru": "how are you",
    "wru": "where are you",
    "hbu": "how about you",
    "wdyk": "what do you know",
    "lmao": "laughing my ass off",
    "bff": "best friend forever",
    "bfs": "best friends",
    "tbh": "to be honest",
    "ngl": "not going to lie",
    "imo": "in my opinion",
    "nvm": "never mind",
    "m8": "mate",
    "otw": "on the way",
    "ik": "i know",
    "lmk": "let me know",
    "tf": "the freak",
    "wya": "where are you",
    "hmu": "hit me up",
    "tmi": "too much information",
    "smh": "shake my head",
    "rn": "right now",
    "dn": "down",
    "nb": "note to self",
    "yk": "you know",
    "dw": "do not worry",
    "wywh": "wish you were here",
    "h8": "hate",
    "gg": "good game",
    "gr8": "great",
    "ttyl": "talk to you later",
    "np": "no problem",
    "sry": "sorry",
    "sup": "what's up",
    "wb": "welcome back",
    "wyd": "what are you doing",
    "wydt": "what are you doing tonight",
    "rly": "really",
    "rt": "retweet",
    "dm": "direct message",
    "omw": "on my way",
    "btw": "by the way",
    "imo": "in my opinion",
    "idk": "i do not know",
    "tbh": "to be honest",
    "ikr": "i know right",
    "lmk": "let me know",
    "lol": "laughing out loud",
    "rofl": "rolling on the floor laughing",
    "brb": "be right back",
    "ily": "i love you",
    "ty": "thank you",
    "imy": "i miss you",
    "yolo": "you only live once",
    "fomo": "fear of missing out",
    "idc": "i do not care",
    "ffs": "for freaks sake",
    "smh": "shake my head",
    "ngl": "not going to lie",
    "wth": "what the hell",
    "abt": "about",
    "gtg": "going to go",
    "nvm": "never mind",
    "cld": "could",
    "ez": "easy",
    "fbm": "fine by me",
    "ftw": "for the win",
    "ik": "i know",

    # Work / productivity / business-style shorthand
    "wfh": "work from home",
    "lmfao": "laughing my freaking ass off",
    "af": "very",
    "aight": "alright",
    "awol": "away without leaving",
    "irl": "in real life",
    "bt": "bad trip",
    "bb": "baby",
    "cu": "see you",
    "idgaf": "i do not give a freak",
    "dgaf": "do not give a freak",
    "df": "the freak",
    "dis": "this",
    "dnt": "do not",
    "dw": "do not worry",
    "enf": "enough",
    "eta": "estimated time of arrival",
    "fwm": "fine with me",
    "fbm": "fine by me",
    "fu": "freak you",
    "fwm": "fine with me",
    "gg": "good game",
    "gn": "good night",
    "gm": "good morning",
    "gr8": "great",
    "grl": "girl",
    "grw": "get ready with me",
    "h8": "hate",
    "hbd": "happy birthday",
    "hbu": "how about you",
    "hru": "how are you",
    "hw": "homework",
    "idts": "i do not think so",
    "ig": "instagram",
    "ilysm": "i love you so much",
    "jk": "just kidding",
    "k": "okay",
    "ldr": "long distance relationship",
    "l2g": "like to go",
    "ly": "love you",
    "mfw": "my face when",
    "m8": "mate",
    "nbd": "no big deal",
    "nsfw": "not safe for work",
    "nm": "nothing much",
    "np": "no problem",
    "nw": "no way",
    "og": "original gangster",
    "ofc": "of course",
    "omg": "oh my god",
    "omfg": "oh my freaking god",
    "ootd": "outfit of the day",
    "otb": "off to bed",
    "otw": "off to work",
    "pm": "private message",
    "ppl": "people",
    "prob": "probably",
    "qt": "cutie",
    "rly": "really",
    "sh": "same here",
    "sis": "sister",
    "bro": "brother",
    "sry": "sorry",
    "sup": "what's up",
    "tbh": "to be honest",
    "thnk": "thank you",
    "thx": "thanks",
    "ttly": "totally",
    "ttyl": "talk to you later",
    "wb": "welcome back",
    "whatevs": "whatever",
    "wyd": "what are you doing",
    "wdyk": "what do you know",
    "wru": "where are you",
    "wtf": "what the freak",
    "wtg": "way to go",
    "wywh": "wish you were here",
    "xd": "laugh",
    "xoxo": "hugs and kisses",
    "xo": "hugs and kisses",
    "y": "why",
    "tryna": "trying to be",
    "iykyk": "if you know you know",
    "wth": "what the hell",
    "wtf": "what the freak",
    "ngl": "not going to lie",
    "pog": "excellent",
    "sussy": "suspicious",
    "goated": "greatest ever",
    "banger": "great hit",
    "mood": "same feeling",
    "peak": "at its best",
    "ratio": "engagement imbalance",
    "yeet": "throw with excitement",
    "meme": "internet joke",
    "bhai": "brother / friend",
    "abey": "hey",
    "nahi": "no",
    "sahi": "correct",
    "thik": "okay",
    "chill": "relax",
    # "aunty": "auntie / older woman",
    # "uncle": "older man",
    "dude": "friend / guy",
    "pookie": "darling",
    "gyaan": "knowledge",
    "waah": "wow",
    "paisa": "money",
    "vibes": "feelings",
    "stuck": "blocked",
    "doom": "bad outcome",
    "dumped": "rejected",
    "crazy": "intense",
    "big yikes": "very embarrassing",
    "bffr": "best friend for real",
}

_MULTILINGUAL_SHORTCUT_MAP = {
    "hi": {
        # Hindi / Hinglish
        "kya": {"canonical": "kya", "native_form": "क्या", "english_meaning": "what"},
        "kr": {"canonical": "kar", "native_form": "कर", "english_meaning": "do"},
        "kro": {"canonical": "karo", "native_form": "करो", "english_meaning": "do it"},
        "nhi": {"canonical": "nahin", "native_form": "नहीं", "english_meaning": "no / not"},
        "ha": {"canonical": "haan", "native_form": "हाँ", "english_meaning": "yes"},
        "haan": {"canonical": "haan", "native_form": "हाँ", "english_meaning": "yes"},
        "bs": {"canonical": "bas", "native_form": "बस", "english_meaning": "just / only / enough"},
        "bss": {"canonical": "bas", "native_form": "बस", "english_meaning": "just / only / enough"},
        "thik": {"canonical": "theek", "native_form": "ठीक", "english_meaning": "okay / correct"},
        "sahi": {"canonical": "sahi", "native_form": "सही", "english_meaning": "correct"},
        "abhi": {"canonical": "abhi", "native_form": "अभी", "english_meaning": "right now"},
        "ruko": {"canonical": "ruko", "native_form": "रुको", "english_meaning": "wait"},
        "mt": {"canonical": "mat", "native_form": "मत", "english_meaning": "do not"},
        "ok": {"canonical": "ok", "native_form": "ओके", "english_meaning": "okay"},
        "chalo": {"canonical": "chalo", "native_form": "चलो", "english_meaning": "let's go"},
        "jldi": {"canonical": "jaldi", "native_form": "जल्दी", "english_meaning": "quickly"},
        "pucho": {"canonical": "pucho", "native_form": "पूछो", "english_meaning": "ask"},
        "gussa": {"canonical": "gussa", "native_form": "गुस्सा", "english_meaning": "angry"},
        "gya": {"canonical": "gaya", "native_form": "गया", "english_meaning": "went"},
        "kch": {"canonical": "kuch", "native_form": "कुछ", "english_meaning": "something"},
        "thnx": {"canonical": "dhanyavaad", "native_form": "धन्यवाद", "english_meaning": "thanks"},
    },
    "bn": {
        "ki": {"canonical": "ki", "native_form": "কি", "english_meaning": "what"},
        "na": {"canonical": "na", "native_form": "না", "english_meaning": "no"},
        "accha": {"canonical": "accha", "native_form": "আচ্ছা", "english_meaning": "okay"},
        "bhalo": {"canonical": "bhalo", "native_form": "ভালো", "english_meaning": "good"},
        "valo": {"canonical": "valo", "native_form": "ভালো", "english_meaning": "good"},
        "kaaj": {"canonical": "kaaj", "native_form": "কাজ", "english_meaning": "work"},
        "sob": {"canonical": "sob", "native_form": "সব", "english_meaning": "all"},
        "kemon": {"canonical": "kemon", "native_form": "কেমন", "english_meaning": "how"},
    },
    "pa": {
        "hun": {"canonical": "hun", "native_form": "ਹੁਨ", "english_meaning": "now"},
        "nahi": {"canonical": "nahi", "native_form": "ਨਹੀਂ", "english_meaning": "no"},
        "shukriya": {"canonical": "shukriya", "native_form": "ਸ਼ੁਕਰੀਆ", "english_meaning": "thank you"},
        "sanu": {"canonical": "sanu", "native_form": "ਸਾਨੂੰ", "english_meaning": "us"},
        "sahi": {"canonical": "sahi", "native_form": "ਸਹੀ", "english_meaning": "correct"},
    },
    "as": {
        "hoi": {"canonical": "hoi", "native_form": "হৈ", "english_meaning": "yes"},
        "bhal": {"canonical": "bhal", "native_form": "ভাল", "english_meaning": "good"},
    },
    "zh": {
        "xie xie": {"canonical": "xie xie", "native_form": "谢谢", "english_meaning": "thank you"},
        "ni hao": {"canonical": "ni hao", "native_form": "你好", "english_meaning": "hello"},
        "wo ai ni": {"canonical": "wo ai ni", "native_form": "我爱你", "english_meaning": "i love you"},
        "hao": {"canonical": "hao", "native_form": "好", "english_meaning": "okay"},
    },
}

_MULTILINGUAL_CANONICAL_MAP = {}
for _lang_map in _MULTILINGUAL_SHORTCUT_MAP.values():
    for _token, _data in _lang_map.items():
        _MULTILINGUAL_CANONICAL_MAP[_token] = _data["canonical"]

_COMBINED_ABBREVIATION_MAP = {
    **_ABBREVIATION_MAP,
    **_MULTILINGUAL_CANONICAL_MAP,
}

_PATTERN = re.compile(
    r"(?i)\b(?:"
    + "|".join(re.escape(k) for k in sorted(_COMBINED_ABBREVIATION_MAP, key=len, reverse=True))
    + r")\b"
)


def _has_abbreviation_match(text: str) -> bool:
    return bool(_PATTERN.search(text))


def normalize_multilingual_shortcut(lang: str, token: str) -> str:
    """Resolve a multilingual shortcut to its canonical same-language form."""
    if not lang or not token:
        return token
    lang_map = _MULTILINGUAL_SHORTCUT_MAP.get(lang.lower())
    if not lang_map:
        return token

    entry = lang_map.get(token.lower())
    return entry["canonical"] if entry else token


def get_shortcut_metadata(lang: str, token: str):
    """Return same-language canonical, native, and English meaning metadata."""
    if not lang or not token:
        return None
    lang_map = _MULTILINGUAL_SHORTCUT_MAP.get(lang.lower())
    if not lang_map:
        return None

    entry = lang_map.get(token.lower())
    if not entry:
        return None

    return {
        "canonical": entry["canonical"],
        "native_form": entry["native_form"],
        "english_meaning": entry["english_meaning"],
    }


def expand_common_english_abbreviations(text: str) -> str:
    """Expand a narrow set of common English abbreviations in mixed-language text."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0).lower()
        return _COMBINED_ABBREVIATION_MAP.get(token, match.group(0))

    return _PATTERN.sub(_replace, text)


def safe_expand_for_model(text: str, model_name: str, source_lang: str) -> str:
    """Safe expansion strategy for social text.

IndicTrans2 is trained for native Indic input and should not be overloaded with
broad rewrites. Only expand known short forms when the input is clearly mixed or
Latin-heavy; otherwise leave native Indic text alone.
"""
    if not text or not _has_abbreviation_match(text):
        return text

    if model_name != "indictrans2":
        return expand_common_english_abbreviations(text)

    # IndicTrans2 should stay conservative. If source is a native Indic language,
    # and the text contains mostly native-script characters with a few English
    # abbreviations, do not rewrite aggressively.
    if source_lang not in {"auto", "und", "mix", "en"}:
        has_latin = bool(re.search(r"[A-Za-z]", text))
        has_native = bool(re.search(r"[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0B00-\u0B7F\u0C00-\u0C7F\u0D00-\u0D7F\u0E00-\u0E7F\u1000-\u109F\u0600-\u06FF]", text))
        if has_native and has_latin:
            return expand_common_english_abbreviations(text)
        return text

    return expand_common_english_abbreviations(text)
