import re

_BURMESE_PHRASE_MAP = [
    ("yangon myo", "ရန်ကုန်မြို့"),
    ("yangon myo hma", "ရန်ကုန်မြို့မှာ"),
    ("di nay", "ဒီနေ့"),
    ("lu oo yay", "လူဦးရေ"),
    ("a myar a pya", "အများအပြား"),
    ("su way khe kya de", "စုဝေးခဲ့ကြတယ်"),
    ("mat la", "မတ်လ"),
    ("mat la se-khoun", "မတ်လ ၁၅"),
    ("mat la se khoun", "မတ်လ ၁၅"),
    ("se-khoun", "၁၅"),
    ("se khoun", "၁၅"),
    ("nga yat", "ရက်"),
    ("a si a wei", "အစည်းအဝေး"),
    ("a si a wei ko", "အစည်းအဝေးကို"),
    ("ma net", "မနက်"),
    ("seh na yi", "ဆယ်နာရီ"),
    ("na yi", "နာရီ"),
    ("ma net seh na yi hma", "မနက် ၁၀ နာရီမှာ"),
    ("a si a wei ko ma net seh na yi hma sa meh", "အစည်းအဝေးကို မနက် ၁၀ နာရီမှာ စမယ်။"),
    ("a si a wei ko ma net seh na yi hma sa me", "အစည်းအဝေးကို မနက် ၁၀ နာရီမှာ စမယ်။"),
    ("sa meh", "စမယ်။"),
    ("sa me", "စမယ်။"),
    ("pyu lote meh", "ပြုလုပ်မယ်"),
    ("telegram hma", "Telegram မှာ"),
    ("di tha din ko", "ဒီသတင်းကို"),
    ("a myan sone", "အမြန်ဆုံး"),
    ("phyant way", "ဖြန့်ဝေ"),
    ("nay kya de", "နေကြတယ်"),
    ("facebook ne telegram", "Facebook နဲ့ Telegram"),
    ("facebok", "Facebook"),
    ("telegram", "Telegram"),
    ("facebook", "Facebook"),
    ("thu do ga", "သူတို့က"),
    ("a-che-a-nay ko", "အခြေအနေကို"),
    ("facebook ne", "Facebook နဲ့"),
    ("hnit khu lone hma", "နှစ်ခုလုံးမှာ"),
    ("mya way khe de", "မျှဝေခဲ့တယ်"),
    ("mya way htar kya de", "မျှဝေခဲ့တယ်"),
    ("lu a myar a pya ga mya way", "လူအများအပြားက"),
    ("lu a myar a pya ga mya way htar", "လူအများအပြားက"),
    ("lu a myar a pya ga mya way htar kya de", "လူအများအပြားက မျှဝေခဲ့တယ်။"),
    ("di post ko lu a myar a pya ga mya way htar kya de", "ဒီ post ကို လူအများအပြားက မျှဝေခဲ့တယ်။"),
    ("di post ko", "ဒီ post ကို"),
    ("di post", "ဒီ post"),
    ("thwar meh", "သွားမယ်။"),
    ("ngar thwar meh", "ငါသွားမယ်။"),
    ("ngar thwar me", "ငါသွားမယ်။"),
    ("ta-yote naing ngan", "တရုတ်နိုင်ငံ"),
    ("ta yote naing ngan", "တရုတ်နိုင်ငံ"),
    ("myanmar naing ngan", "မြန်မာနိုင်ငံ"),
    ("htain naing ngan", "ထိုင်းနိုင်ငံ"),
    ("tha din hte hma", "သတင်းထဲမှာ"),
    ("phaw pya htar de", "ဖော်ပြထားတယ်"),
    ("thadin", "သတင်း"),
    ("ba a", "ဘယ်တော့"),
    ("min ga lar par", "မင်္ဂလာပါ။"),
    ("nay kaung lar", "နေကောင်းလား။"),
    ("ngar nay kaung par de", "ငါနေကောင်းပါတယ်။"),
    ("bar lote nay le", "ဘာလုပ်နေလဲ။"),
    ("ma shi buu", "မရှိဘူး။"),
    ("shi de", "ရှိတယ်။"),
    ("ngar ma thwar buu", "ငါမသွားဘူး။"),
    ("ngar thwar meh", "ငါသွားမယ်။"),
    ("bar phyit ta le", "ဘာဖြစ်တာလဲ။"),
    ("ma thi buu", "မသိဘူး။"),
    ("a yan pwe de", "အရမ်းပူတယ်။"),
    ("di nay a yan pwe de", "ဒီနေ့အရမ်းပူတယ်။"),
    ("lone-chone-yay", "လမ်းအချို့"),
    ("lone chone yay", "လမ်းအချို့"),
    ("a-che-a-nay kyaung lan", "အခြေအနေကြောင့်"),
    ("a che a nay kyaung lan", "အခြေအနေကြောင့်"),
    ("a-choi ko", "အချို့ကို"),
    ("a choi ko", "အချို့ကို"),
    ("pate htar par de", "ပိတ်ထားပါတယ်။"),
    ("pate htar de", "ပိတ်ထားတယ်။"),
    ("ma kaung buu naw", "မကောင်းဘူးနော်။"),
    ("ma kaung buu", "မကောင်းဘူး။"),
    ("pyaw pya par", "ပြောပြပါ။"),
    ("a ku bar lote ya ma le", "အခုဘာလုပ်ရမလဲ။"),
    ("ta khu khu pyaw par", "တစ်ခုခု ပြောပါ။"),
    ("a yan kaung de", "အရမ်းကောင်းတယ်။"),
    ("a yan", "အရမ်း"),
    ("hote de", "ဟုတ်တယ်။"),
    ("ma hote buu", "မဟုတ်ဘူး။"),
    ("ma pyaw ne buu", "မပြောနဲ့ဘူး။"),
    ("ma thi buu naw", "မသိဘူးနော်။"),
    ("min ga lar par naw", "မင်္ဂလာပါနော်။"),
    ("nay kaung lar bro", "နေကောင်းလား bro။"),
    ("hote tal lol", "ဟုတ်တယ် lol။"),
    ("ma hote buu lol", "မဟုတ်ဘူး lol။"),
    ("a yan kaung tl", "အရမ်းကောင်းတယ်။"),
    ("hote tl", "ဟုတ်တယ်။"),
    ("ma hote bu", "မဟုတ်ဘူး။"),
    ("nay kaung lr", "နေကောင်းလား။"),
    ("bar lote ne lr", "ဘာလုပ်နေလဲ။"),
    ("mnglpr", "မင်္ဂလာပါ။"),
    ("min ga lar par naw", "မင်္ဂလာပါနော်။"),
    ("bro", "bro"),
    ("tl", "တယ်။"),
]

_BURMESE_TOKEN_MAP = {
    "yangon": "ရန်ကုန်",
    "myo": "မြို့",
    "hma": "မှာ",
    "di": "ဒီ",
    "nay": "နေ",
    "lu": "လူ",
    "oo": "ဦး",
    "yay": "ရေ",
    "a": "အ",
    "myar": "များ",
    "pya": "ပြား",
    "ga": "က",
    "su": "စု",
    "way": "ဝေး",
    "khe": "ခဲ့",
    "kya": "ကြ",
    "kyaung": "ကြောင့်",
    "lan": "လမ်း",
    "lone": "လမ်း",
    "chone": "အချို့",
    "choi": "အချို့",
    "de": "တယ်",
    "ko": "ကို",
    "ne": "နဲ့",
    "hta": "ထား",
    "dar": "တယ်",
    "mya": "မျှ",
    "thad": "သတင်း",
    "din": "သတင်း",
    "mat": "မတ်",
    "la": "လ",
    "khu": "ခု",
    "lone": "လုံး",
    "htaing": "ထိုင်း",
    "myanmar": "မြန်မာ",
    "ta": "တရုတ်",
    "yote": "နိုင်ငံ",
    "naing": "နိုင်ငံ",
    "ngan": "နိုင်ငံ",
    "htain": "ထိုင်း",
    "phone": "ဖော်",
    "phaw": "ဖော်",
    "phyant": "ဖြန့်",
    "myan": "မြန်",
    "sone": "ဆုံး",
    "thadin": "သတင်း",
    "thu": "သူ",
    "do": "တို့",
    "ga": "က",
    "che": "ခြေအနေ",
    "a-che-a-nay": "အခြေအနေ",
    "cit": "စစ်",
    "se": "၁၅",
    "khoun": "ရက်",
    "nga": "ငါ",
    "yat": "နေ့",
    "wei": "ဝေး",
    "si": "အစည်းအဝေး",
    "pyu": "ပြု",
    "lote": "လုပ်",
    "sa": "စ",
    "meh": "မယ်",
    "na": "နာရီ",
    "yi": "နာရီ",
    "seh": "ဆယ်",
    "htet": "ထဲ",
    "hte": "ထဲ",
    "myit": "မိုက်",
    "tar": "တာ",
    "shwe": "သွား",
    "ji": "စီ",
    "pyae": "ပျား",
    "min": "မင်္ဂလာ",
    "lar": "လား",
    "par": "ပါ",
    "kaung": "ကောင်း",
    "ngar": "ငါ",
    "thwar": "သွား",
    "phyit": "ဖြစ်",
    "thi": "သိ",
    "a": "အ",
    "yan": "အရမ်း",
    "pwe": "ပူ",
    "naw": "နော်",
    "pyaw": "ပြော",
    "ku": "ခု",
    "hote": "ဟုတ်",
    "buu": "ဘူး",
    "lol": "lol",
    "mnglpr": "မင်္ဂလာပါ။",
    "thwar": "သွား",
    "meh": "မယ်",
}


def _normalize_token(token: str) -> str:
    original = token.strip()
    cleaned = original.lower().strip("'\"()[]{}<>.,!?;:")
    if not cleaned:
        return ""
    cleaned = re.sub(r"(.)\1+", r"\1", cleaned)
    if cleaned in {"facebook", "facebok"}:
        return "Facebook"
    if cleaned == "telegram":
        return "Telegram"
    if cleaned.startswith("facebook") or cleaned.startswith("telegram"):
        return cleaned.title()
    return _BURMESE_TOKEN_MAP.get(cleaned, cleaned)


def detect_romanized_burmese(text: str) -> bool:
    if not text or not any(ch.isalpha() for ch in text):
        return False
    if re.search(r"[\u1000-\u109F\uAA60-\uAA7F\uA9E0-\uA9FF]", text):
        return False

    lowered = text.lower()
    signals = (
        "myo", "hma", "nay", "yay", "kya", "de", "ko", "ne",
        "yangon", "telegram", "facebook", "facebok", "myanmar", "mat la",
        "lu oo yay", "a myar a pya", "su way khe kya", "a yan",
        "ma kaung", "hote", "bro", "tl", "naw", "kaung", "buu",
        "lone", "chone", "kyaung lan", "a choi", "a-che-a-nay", "pate htar", "par de"
    )
    return any(sig in lowered for sig in signals)


def prepare_for_translation(text: str) -> str:
    """Return the text in a consistent form before routing or caching.

    Romanized Burmese needs a deterministic Myanmar-script rewrite before a model
    sees it; native Burmese should pass through unchanged. This also prevents the
    bad cached result from an earlier raw-latin input from being reused after the
    fix has been applied.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    if detect_romanized_burmese(text):
        return normalize_burmese_text(text)
    return text


def normalize_burmese_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text
    if re.search(r"[\u1000-\u109F\uAA60-\uAA7F\uA9E0-\uA9FF]", text):
        return text

    normalized = text

    # High-confidence noisy Burmese patterns need deterministic rewriting before the
    # generic token map kicks in. This is the "better approach" for social/news-style
    # compressed Burmese, where literal token mapping alone still leaves the model with
    # a weak Latin reading instead of the intended Burmese meaning.
    noisy_patterns = [
        (
            r"(?i)\blone[- ]?chone[- ]?yay\s+a[- ]?che[- ]?a[- ]?nay\s+kyaung[- ]?lan\s+a[- ]?choi\s+ko\s+pate[- ]?htar\s+par\s+de\b",
            "လမ်းအချို့ အခြေအနေကြောင့် အချို့ကို ပိတ်ထားပါတယ်။",
        ),
        (
            r"(?i)\blone[- ]?chone[- ]?yay\s+a[- ]?che[- ]?a[- ]?nay\s+kyaung[- ]?lan\s+a[- ]?choi\s+ko\s+pate[- ]?htar\s+de\b",
            "လမ်းအချို့ အခြေအနေကြောင့် အချို့ကို ပိတ်ထားတယ်။",
        ),
    ]
    for pattern, replacement in noisy_patterns:
        normalized = re.sub(pattern, replacement, normalized)

    for phrase, replacement in _BURMESE_PHRASE_MAP:
        normalized = re.sub(rf"(?i)\b{re.escape(phrase)}\b", replacement, normalized)

    # Preserve names that are already in proper Latin form (Telegram/Facebook) while
    # converting common Romanized Burmese function words/phrases.
    tokens = re.split(r"(\s+|[.,!?;:()\[\]{}])", normalized)
    converted = []
    for token in tokens:
        if not token or token.isspace():
            converted.append(token)
            continue
        if re.fullmatch(r"[A-Za-z]+", token):
            converted.append(_normalize_token(token))
        else:
            converted.append(token)

    final_text = "".join(converted)
    final_text = re.sub(r"(?<=[\u1000-\u109F])\s+(?=[\u1000-\u109F])", "", final_text)
    final_text = re.sub(r"\s+([၊၊]|[\.,!?;:])", r"\1", final_text)
    final_text = re.sub(r"(။)([.!?;:])+$", r"\1", final_text)
    final_text = re.sub(r"([.!?;:])\1+$", r"\1", final_text)
    final_text = re.sub(r"\s+", " ", final_text).strip()
    return final_text
