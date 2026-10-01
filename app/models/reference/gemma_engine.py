#!/usr/bin/env python3
"""
gemma.py
--------
Core translation engine for a Gemma model served locally via vLLM's
OpenAI-compatible API. Auto-detects language + script (native, romanized,
or code-mixed) and translates to a target language. Supports an optional
manual source-language override for when auto-detection is uncertain.

Importable by translate_ui.py (FastAPI UI) and usable standalone as a CLI.
"""

import argparse
import concurrent.futures
import json
import ast
import logging
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

# --------------------------------------------------------------------------- #
# Confirmed working server config (from: curl http://localhost:30004/v1/models)
# --------------------------------------------------------------------------- #
DEFAULT_BASE_URL = "http://localhost:30004/v1"
DEFAULT_MODEL_NAME = "gemma-4-26b-a4b-it"
DEFAULT_API_KEY = "not-needed"
DEFAULT_TARGET_LANG = "en"


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gemma")


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You are a precise multilingual language-identification and translation engine.

You will receive a single piece of user-generated text (social media / chat / news style).
The text may be in any of the following forms
  1. Native script of any language (e.g. Devanagari, Arabic, Cyrillic, Han, Bengali/Meitei, etc.)
  2. Romanized / transliterated script (the language written using Latin letters,
     e.g. Hindi written as "aj PM Modi ne BRICS summit me participate kiya")
  3. Code-mixed / mixed script (two or more languages or scripts combined in one
     sentence, e.g. Hinglish, Spanglish, Arabizi)
  4. Already in the target language

SPECIAL CASES: Romanized and mixed-script South Asian / Perso-Arabic languages.
  - Burmese (Myanmar):
      * If the input is written in native Myanmar script, translate directly.
      * If the input is Romanized Burmese, first reconstruct the intended Burmese meaning in native Myanmar script before translating to English.
      * Romanized Burmese may contain phonetic spelling, missing vowels, social-media shortcuts, slang, abbreviations, repeated letters, emojis, and English words mixed with Burmese.
      * Do not translate the romanization itself as if it were English. Interpret the Burmese meaning first, then translate that meaning into natural English.
      * For mixed Burmese-English text, translate the Burmese content while keeping appropriate English names and brand terms intact.
  - Pashto / Balochi / Divehi:
      * If the input is written in native Perso-Arabic script, translate directly.
      * If the input is Romanized Pashto, Balochi, or Divehi, first reconstruct the intended native-script form in that language before translating to English.
      * Do NOT assume Urdu or Arabic by default just because the script is Perso-Arabic. Distinguish Pashto, Balochi, and Divehi using actual vocabulary, function words, and grammar.
      * Preserve the original meaning instead of translating the Latin transliteration word-by-word.
  - Generic rule:
      * For all romanized/transliterated inputs, internalize the target language's native-script meaning first, then translate that meaning into natural English.
      * Return only the English translation, not any notes or transliteration.

IMPORTANT - identify the language in two steps, don't skip step 1:
  Step 1. Identify the SCRIPT (the writing system: Devanagari, Perso-Arabic,
    Bengali script, Gurmukhi, Latin, etc.). This narrows down the candidates
    but does NOT by itself tell you the language - several unrelated
    languages can share one script.
  Step 2. Within that script, identify the SPECIFIC language using actual
    vocabulary, function words, and grammar in the text - never assume the
    "most common" or "most likely" language for that script by default.
    Many scripts are shared by multiple languages that are easy to confuse
    if you skip this step, for example:
      - Devanagari script: Hindi, Marathi, Nepali, Sanskrit, Maithili,
        Konkani, Bodo, Dogri all use it. Look for distinguishing markers,
        e.g. Marathi's characteristic postpositions/verb endings
        (आहे, -ला, -चा/ची/चे) vs Hindi's (है, को, का/की/के); Nepali's
        distinct verb forms (छ, हो) vs Hindi; Sanskrit's classical/verse
        register and case endings vs modern conversational Hindi.
      - Perso-Arabic script: Urdu, Punjabi (Shahmukhi), Sindhi, Pashto,
        Balochi, Divehi, Kashmiri, and Arabic/Persian/Dari all use variants of it.
        Do not default to Urdu or Arabic just because the script looks
        Perso-Arabic - check for language-specific letters, vocabulary and
        grammar. For romanized Pashto, Balochi, and Divehi, use the actual
        vocabulary and phrase patterns (for example Pashto markers such as
        'zama', 'khpal', 'khwa', 'da', 'sta'; Balochi markers such as
        'balochi', 'baloch', 'zaban', 'ham', 'khan'; Divehi markers such as
        'dhivehi', 'divehi', 'hithu', 'faharu', 'vanee') instead of
        assuming Urdu or Arabic. Persian/Dari verbs and vocabulary differ from
        Urdu's Hindi-derived core vocabulary.
      - Bengali script: Bengali, Assamese, and Manipuri/Meitei all use it
        (Meitei also has its own native Meitei Mayek script). Assamese has
        distinct sounds/spellings (e.g. ৰ, ৱ) and vocabulary vs Bengali;
        Meitei vocabulary and grammar are unrelated to both even when
        written in Bengali script.
      - Latin script: when text is fully in Latin letters, first decide if
        it's "latin_native" (a language that is natively written in Latin,
        e.g. English, Spanish, French, Vietnamese, Malay/Indonesian) or
        "romanized" (a non-Latin-script language typed phonetically in
        Latin letters, e.g. Hindi/Urdu/Arabic/Tamil written with English
        letters). For romanized text, judge by vocabulary and sentence
        structure, not by any single ambiguous word.
      - Romanized Hindi vs Urdu: when spoken casually and romanized, Hindi
        and Urdu are often near-identical in everyday vocabulary. Default
        to Hindi ("hi") unless the text contains vocabulary or phrasing
        that is distinctly Perso-Arabic/Urdu in register (not just a single
        loanword, which occurs in both).
      - Do not let names, hashtags, or @mentions in other languages/scripts
        bias your decision - base the language purely on the actual
        sentence content (the grammar and everyday vocabulary), not on
        proper nouns, brand names, or code-mixed English tech/social-media
        terms that appear in text of almost any language.

Your job:
  - If a source-language hint is given below, treat that as the confirmed language
    (skip guessing the language itself, but still determine script_type from the text
    using the same script-identification logic above).
  - Otherwise, detect the ACTUAL language(s) and script used in the text (ignore any
    language label given to you elsewhere - decide purely from the text content,
    following the two-step process above).
  - Classify script_type as exactly one of: "native", "romanized", "mixed", "latin_native"
    ("latin_native" = the text is natively written in Latin script, e.g. English/Spanish/etc.,
    as opposed to "romanized" which means a non-Latin-script language typed in Latin letters).
  - If you are genuinely torn between two closely related languages that share a
    script, pick the one whose distinguishing vocabulary/grammar markers (as
    described above) actually appear in the text, rather than the more
    statistically common language for that script/region.
  - Before writing the translation, list every named entity, official title, organization,
    event, program/scheme, and date found in the source into source_entities, in the literal
    English form you are about to use for each. Commit to these forms first - the translation
    must then use each one exactly as listed in source_entities, not a different, more
    familiar-sounding real-world name or concept you associate with the topic.
  - Translate the full text into the target language in decent, plain, neutral, clear, and understandable standard English prose while preserving the exact contextual meaning.
  - CRITICAL STYLE RULE: The translated text MUST NOT use Gen-Z style slang, internet jargon, or overly informal colloquialisms (e.g. do NOT use terms like "GOAT", "slay", "banger", "no cap", "fr fr", "sus", "lit", "fire", etc.).
  - Translate all social media slangs, local abbreviations, and informal expressions into standard, neutral, clear English equivalents that accurately capture the original intent (e.g., translate Chinese 'YYDS' or slang meaning 'the best' as 'the absolute best' or 'outstanding', NOT 'the GOAT'). Preserve named entities, official titles, organizations, government schemes/programs, event names, dates, and numbers exactly as they appear in the source. Keep recurring terms translated the same way every time they appear, and do not invent, infer, or drop information that changes the source's meaning.
  - Do NOT translate or alter: URLs, @mentions, #hashtags, emoji, markdown symbols
    (like ** or -----), or code/identifiers. Keep them exactly as-is, in place.
  - If the text is already fully in the target language, still return it (unchanged or
    lightly normalized) as translated_text.

Two examples of the exact mistake to avoid - substituting a different, more "familiar" real-world
name/concept instead of the literal source meaning:
  Source event name literally means "Tchaikovsky Life and Achievements Exhibition."
    WRONG: "Tchaikovsky Birth Centenary Exhibition" (a different, invented event)
    RIGHT: "Tchaikovsky Life and Achievements Exhibition"
  Source program name literally means "China-Russia Education Year."
    WRONG: "Sino-Russian Year of Education" (a reworded paraphrase, not the literal name)
    RIGHT: "China-Russia Education Year"

Respond with ONLY a single JSON object, no markdown fences, no commentary, no chain-of-thought,
in exactly this shape:

{"detected_language": "<ISO 639-1 code, or best-guess name if unknown>", "detected_language_name": "<human readable language name>", "script_type": "native" | "romanized" | "mixed" | "latin_native", "mixed_components": ["<lang1>", "<lang2>"], "source_entities": ["<entity as it appears/means in the source, in its literal English form>", ...], "translated_text": "<full translation in the target language>"}

"mixed_components" must be an empty list [] if script_type is not "mixed". "source_entities" must
be an empty list [] if the text contains no named entities/titles/dates worth flagging.
CRITICAL - VALID JSON ONLY: this output will be parsed by a strict JSON parser. Any double-quote
character that appears INSIDE a string value (e.g. a quoted term like "HIMARS" within
translated_text) MUST be escaped as \" - never leave a bare " inside a string value, and never
wrap a value in extra/triple quotes. If in doubt, prefer rewording to avoid an internal quote
entirely rather than risk invalid JSON.
Output ONLY the JSON object above. Do not think out loud, do not explain your reasoning,
do not add any text before or after the JSON.
"""

USER_PROMPT_TEMPLATE = """Target language for translation: {target_lang}
{source_hint_line}{glossary_hint}
Text to analyze and translate:
\"\"\"{text}\"\"\"
"""

# Optional glossary of recurring domain-specific entities (source term -> required English
# form). This sidesteps the model's recall/grounding gap entirely for anything you've already
# seen before, instead of relying on it to correctly recall an obscure entity from its own
# weights. Populate with terms specific to your own content (e.g. recurring place names,
# government schemes, organizations) - matched as plain substrings against the input text.
ENTITY_GLOSSARY: Dict[str, str] = {
    # Common English social-media abbreviations and shortcuts
    "TBH": "to be honest",
    "FYI": "for your information",
    "BTW": "by the way",
    "IMO": "in my opinion",
    "ASAP": "as soon as possible",
    "Pls": "please",
    "pls": "please",
    "PLS": "please",
    "thx": "thank you",
    "THX": "thank you",
    "Tx": "thank you",
    "tx": "thank you",
    "Tks": "thanks",
    "tks": "thanks",
    "Tkx": "thanks",
    "tkx": "thanks",
    "u": "you",
    "r": "are",
    "ur": "your",
    "omg": "oh my god",
    "OMG": "oh my god",
    "wtf": "what the hell",
    "WTF": "what the hell",
    "lol": "laughing out loud",
    "LOL": "laughing out loud",
    "lmao": "laughing my ass off",
    "LMAO": "laughing my ass off",
    "rofl": "rolling on the floor laughing",
    "ROFL": "rolling on the floor laughing",
    "brb": "be right back",
    "BRB": "be right back",
    "b4": "before",
    "B4": "before",
    "b/c": "because",
    "BC": "because",
    "cya": "see you",
    "CYA": "see you",
    "sry": "sorry",
    "SRY": "sorry",
    "pls2": "please",
    "plz": "please",
    "PLZ": "please",
    "noob": "newbie",
    "NOOB": "newbie",
    "gud": "good",
    "GUD": "good",
    "gr8": "great",
    "GR8": "great",
    "wanna": "want to",
    "Wanna": "want to",
    "gonna": "going to",
    "Gonna": "going to",
    "gotta": "got to",
    "Gotta": "got to",
    "idk": "I do not know",
    "IDK": "I do not know",
    "ikr": "I know, right",
    "IKR": "I know, right",
    "smh": "shaking my head",
    "SMH": "shaking my head",
    "yolo": "you only live once",
    "YOLO": "you only live once",
    "fyi": "for your information",
    "Fyi": "for your information",
    "np": "no problem",
    "NP": "no problem",
    "nvm": "never mind",
    "NVM": "never mind",
    "rn": "right now",
    "RN": "right now",
    "dm": "direct message",
    "DM": "direct message",
    "msg": "message",
    "MSG": "message",
    "bc": "because",
    "BC": "because",
    "fr": "for real",
    "FR": "for real",
    "u2": "you too",
    "U2": "you too",
    "pls": "please",
    "pls": "please",

    # Common Burmese Romanized social shortcuts and conversational particles
    "hma": "မှာ",
    "ko": "ကို",
    "ne": "နဲ့",
    "myo": "မြို့",
    "yay": "ရေ",
    "nay": "နေ့",
    "de": "တယ်",
    "meh": "မယ်",
    "buu": "ဘူး",
    "lar": "လား",
    "naw": "နော်",
    "bro": "bro",
    "tl": "တယ်",
    "lol": "laughing out loud",
    "hote": "ဟုတ်တယ်",
    "ma hote buu": "မဟုတ်ဘူး",
    "min ga lar par": "မင်္ဂလာပါ။",
    "nay kaung lar": "နေကောင်းလား။",
    "ngar nay kaung par de": "ငါနေကောင်းပါတယ်။",
    "bar lote nay le": "ဘာလုပ်နေလဲ။",
    "ma shi buu": "မရှိဘူး။",
    "shi de": "ရှိတယ်။",
    "ngar ma thwar buu": "ငါမသွားဘူး။",
    "ngar thwar meh": "ငါသွားမယ်။",
    "bar phyit ta le": "ဘာဖြစ်တာလဲ။",
    "ma thi buu": "မသိဘူး။",
    "di nay a yan pwe de": "ဒီနေ့အရမ်းပူတယ်။",
    "a yan kaung de": "အရမ်းကောင်းတယ်။",
    "ma kaung buu naw": "မကောင်းဘူးနော်။",
    "pyaw pya par": "ပြောပြပါ။",
    "a ku bar lote ya ma le": "အခုဘာလုပ်ရမလဲ။",
}


# Sentence-ending punctuation across every script this project routes to
# Gemma: Latin/Cyrillic (. ! ?), Devanagari danda/double-danda (। ॥), and
# CJK full-width forms (。！？). \s* (not \s+) after the lookbehind because
# CJK text has no spaces between sentences at all - requiring whitespace
# there would mean the split simply never fires for Chinese/Japanese text.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[।॥.!?。！？])\s*")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:—-])\s+")


def split_text_for_translation(text: str, max_chars: int = 1800) -> List[str]:
    """Splits long text into chunks for translation, one sentence-aware chunk
    per Gemma call, so a single very long document (confirmed real case:
    2500-3500 token Telegram/Facebook digest posts) becomes several small,
    fast, reliable calls instead of one large call gambling on finishing
    before the wall-clock timeout.

    Sized by CHARACTER count, not word count - a word-count measure is
    meaningless for CJK text, which has no spaces between words (confirmed
    real case: a Chinese news article among the failing inputs). Character
    count is a consistent size proxy across every script.

    Never breaks a sentence or word to make a chunk fit. Falls back, only if
    a single sentence alone exceeds max_chars, to splitting at clause
    punctuation, then at word boundaries (space-delimited scripts). Only in
    the extreme case of one oversized "word" with no spaces at all (e.g. a
    giant CJK run with no punctuation) does it fall back to a raw character
    slice - there is no other safe boundary to use at that point.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    atomic_units: List[str] = []

    for para in paragraphs:
        for sentence in _SENTENCE_SPLIT_RE.split(para):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                atomic_units.append(sentence)
                continue

            # Oversized single sentence - try clause-level boundaries next.
            for clause in _CLAUSE_SPLIT_RE.split(sentence):
                clause = clause.strip()
                if not clause:
                    continue
                if len(clause) <= max_chars:
                    atomic_units.append(clause)
                    continue

                # Still oversized - fall back to word boundaries if the
                # clause actually has spaces to split on.
                words = clause.split(" ")
                if len(words) > 1:
                    current_words: List[str] = []
                    current_len = 0
                    for word in words:
                        added = len(word) + (1 if current_words else 0)
                        if current_words and current_len + added > max_chars:
                            atomic_units.append(" ".join(current_words))
                            current_words = [word]
                            current_len = len(word)
                        else:
                            current_words.append(word)
                            current_len += added
                    if current_words:
                        atomic_units.append(" ".join(current_words))
                else:
                    # No spaces at all (e.g. one giant CJK run with no
                    # punctuation) - character slicing is the only option
                    # left that guarantees a bounded chunk size.
                    for i in range(0, len(clause), max_chars):
                        atomic_units.append(clause[i:i + max_chars])

    # Greedily pack sentences (or their fallback pieces) into chunks up to
    # max_chars, so several short sentences share one chunk/request instead
    # of each becoming its own tiny call.
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0
    for unit in atomic_units:
        added = len(unit) + (1 if current_chunk else 0)
        if current_chunk and current_len + added > max_chars:
            chunks.append(" ".join(current_chunk))
            current_chunk = [unit]
            current_len = len(unit)
        else:
            current_chunk.append(unit)
            current_len += added
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def build_glossary_hint(text: str, glossary: Optional[Dict[str, str]] = None) -> str:
    """Returns a prompt snippet listing only the glossary entries that actually appear in
    `text`, or "" if none match / no glossary is configured."""
    glossary = glossary if glossary is not None else ENTITY_GLOSSARY
    hits = {k: v for k, v in glossary.items() if k in text}
    if not hits:
        return ""
    lines = "\n".join(f'  "{k}" -> "{v}"' for k, v in hits.items())
    return f"\nKnown entities in this text and their required English form (use exactly):\n{lines}\n"


def build_messages(
    text: str,
    target_lang: str,
    source_lang_hint: Optional[str] = None,
    glossary: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    hint_line = (
        f"Source-language hint (confirmed by user, do not re-guess the language): {source_lang_hint}"
        if source_lang_hint
        else ""
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                target_lang=target_lang,
                source_hint_line=hint_line,
                glossary_hint=build_glossary_hint(text, glossary),
                text=text,
            ),
        },
    ]


# --------------------------------------------------------------------------- #
# Robust JSON extraction from model output
# --------------------------------------------------------------------------- #
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _repair_unescaped_quotes(raw: str) -> str:
    """Heuristic repair for a real failure mode seen on long, quote-heavy
    translations: the model writes a literal, unescaped " inside a string value
    (e.g. a quoted term like "HIMARS" embedded in translated_text) instead of \".
    Standard json.loads treats that quote as ending the string early and then
    chokes on whatever comes after.

    Walks the raw text tracking whether we're inside a JSON string value. On an
    unescaped quote, only treats it as a real string terminator if what
    immediately follows (skipping whitespace) is a JSON structural character
    (, } ] or :) - otherwise it's a stray quote inside the value, so it gets
    escaped instead. This is a heuristic, not a full JSON grammar, but it
    correctly handles the observed pattern of quoted terms embedded in prose."""
    out = []
    in_string = False
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\\" and in_string and i + 1 < n:
            # Preserve existing escape sequences verbatim.
            out.append(ch)
            out.append(raw[i + 1])
            i += 2
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                out.append(ch)
                i += 1
                continue
            j = i + 1
            while j < n and raw[j] in " \t\r\n":
                j += 1
            if j >= n or raw[j] in ",}]:":
                in_string = False
                out.append(ch)
            else:
                out.append('\\"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: model may emit a Python-style dict (single quotes).
    try:
        obj = ast.literal_eval(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    candidate = raw
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # Last resort: repair likely-unescaped internal quotes and retry.
    try:
        return json.loads(_repair_unescaped_quotes(candidate))
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# Entity verification + repair (best-effort quality pass)
# --------------------------------------------------------------------------- #
# Known limitation this exists for: Gemma 26B can substitute a named entity or
# official title with a different, more "familiar" real-world concept it
# associates with the topic (e.g. translating an exhibition literally named
# "lifetime achievement exhibition" as "Tchaikovsky Centenary Exhibition").
# Likely a recall/grounding gap rather than a prompt-compliance issue - this is
# an MoE build (~4B active params per token), so for less-common entities it
# tends to fall back on the most familiar association instead of faithfully
# carrying the literal source components. Multiple attempts to PREVENT this via
# the main SYSTEM_PROMPT alone did not fix it and slightly hurt overall
# quality, so instead this runs a second, narrowly-scoped call to DETECT it
# after the fact (verify_entities), and - only when something is actually
# found - a third call to fix JUST the flagged entities (repair_entities)
# without touching the rest of the translation. Both are best-effort and
# never raise or block the primary translation on failure.
VERIFY_SYSTEM_PROMPT = """You are a translation quality checker specializing in named-entity
accuracy. You will be given a source text and its English translation. Your ONLY job is to check
whether named entities - people, organizations, locations, government programs/schemes, events,
institutions, product names, and official titles - were translated accurately: does the English
wording reflect the literal meaning/components of the corresponding source entity, rather than
being replaced with a different, more familiar-sounding real-world name or concept?

Do NOT re-translate the text. Do NOT comment on style, fluency, grammar, or word order. Only
flag entities whose MEANING appears to have been changed, substituted, or invented.

Respond with ONLY a single JSON object, no markdown fences, no commentary, in exactly this shape:

{"entity_issues": ["<short description of one specific mismatched entity, e.g. 'source event name literally means X but translation says Y'>", ...]}

Return {"entity_issues": []} if you find no such issues.
"""


def verify_entities(
    client: OpenAI,
    model: str,
    source_text: str,
    translated_text: str,
) -> Dict[str, Any]:
    """Best-effort check: does the translation preserve named-entity meaning?

    Never raises - this is a bonus quality signal, not a requirement for the
    translation itself to succeed. Returns {"entity_issues": []} on any
    failure (timeout, unparseable response, etc.)."""
    if not translated_text or not translated_text.strip():
        return {"entity_issues": []}

    messages = [
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f'Source text:\n"""{source_text}"""\n\nTranslation:\n"""{translated_text}"""',
        },
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            tool_choice="none",
        )
        raw = response.choices[0].message.content or ""
        parsed = extract_json(raw)
        if parsed is not None and isinstance(parsed.get("entity_issues"), list):
            return {"entity_issues": [str(i) for i in parsed["entity_issues"]]}
    except Exception as e:
        logger.warning("Entity verification failed (non-fatal): %s", e)
    return {"entity_issues": []}


REPAIR_SYSTEM_PROMPT = """You will be given a source text, a translation of it, and a list of
specific named-entity problems found in that translation. Regenerate the translation, fixing
ONLY the listed entity problems. Do not change anything else - keep the rest of the wording,
structure, and style exactly as it was. Preserve entities using their literal source components
or standard English form, never a different real-world concept you associate with the topic.

Respond with ONLY the corrected translation text. No JSON, no commentary."""


def repair_entities(
    client: OpenAI,
    model: str,
    source_text: str,
    translated_text: str,
    entity_issues: List[str],
) -> str:
    """Best-effort targeted fix for the specific entity problems verify_entities() found.

    Only fires when there's actually something to fix, and only rewrites the flagged
    entities rather than re-translating from scratch - never raises; on any failure this
    just returns the original translated_text unchanged."""
    if not entity_issues:
        return translated_text

    issues_str = "\n".join(f"- {i}" for i in entity_issues)
    messages = [
        {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f'Source text:\n"""{source_text}"""\n\n'
                f'Translation:\n"""{translated_text}"""\n\n'
                f"Entity problems found:\n{issues_str}"
            ),
        },
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=1024,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            tool_choice="none",
        )
        fixed = (response.choices[0].message.content or "").strip()
        return fixed or translated_text
    except Exception as e:
        logger.warning("Entity repair failed (non-fatal): %s", e)
        return translated_text


# --------------------------------------------------------------------------- #
# Model call with retries
# --------------------------------------------------------------------------- #
def _do_call(
    client: OpenAI,
    model: str,
    text: str,
    target_lang: str,
    source_lang_override: Optional[str],
    temperature: float,
    disable_thinking: bool,
    tool_choice_none: bool,
):
    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=build_messages(text, target_lang, source_lang_override),
        temperature=temperature,
        # Was 8192. Covers this model's internal "thinking"/reasoning tokens
        # AND the final answer combined, not just translation output - a
        # documented failure mode already exists where reasoning alone can
        # exhaust the budget before any answer is produced (see the
        # disable_thinking comment below), so this is a moderate cut, not an
        # aggressive one, to avoid making that worse. Chunking now keeps
        # inputs to ~1800 chars, so a much smaller output budget than 8192
        # is still generous for the translation itself.
        max_tokens=4096,
    )
    extra_body: Dict[str, Any] = {}
    if disable_thinking:
        # This Gemma4 build does chain-of-thought "thinking" before the final
        # answer (visible via a separate "reasoning" field on the message).
        # On some inputs it finishes (finish_reason=stop) having only produced
        # reasoning and never the actual JSON answer, leaving content empty
        # regardless of max_tokens. Disabling thinking via the chat template
        # forces it straight to the final answer.
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    if extra_body:
        kwargs["extra_body"] = extra_body
    if tool_choice_none:
        # The server was launched with --enable-auto-tool-choice
        # --tool-call-parser gemma4, which can make the model route its JSON
        # answer into a tool_call instead of plain content. tool_choice="none"
        # prevents that.
        kwargs["tool_choice"] = "none"
    return client.chat.completions.create(**kwargs)


def call_model(
    client: OpenAI,
    model: str,
    text: str,
    target_lang: str,
    source_lang_override: Optional[str] = None,
    max_retries: int = 3,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Detect language/script and translate `text` to `target_lang`.

    source_lang_override: pass an ISO code (e.g. "hi") to force the source
    language when auto-detection is uncertain or wrong. Leave None/empty to
    auto-detect.
    """
    if not text or not text.strip():
        return {
            "detected_language": source_lang_override or None,
            "detected_language_name": None,
            "script_type": None,
            "mixed_components": [],
            "translated_text": text,
        }

    # Strategies to try in order, each attempted with retries before moving on.
    # 1) disable thinking + tool_choice none (best case: fast, direct JSON)
    # 2) disable thinking only (in case tool_choice isn't accepted here)
    # 3) plain call (last resort, in case chat_template_kwargs isn't supported)
    strategies = [
        {"disable_thinking": True, "tool_choice_none": True},
        {"disable_thinking": True, "tool_choice_none": False},
        {"disable_thinking": False, "tool_choice_none": False},
    ]

    last_err: Optional[Exception] = None
    for strategy in strategies:
        for attempt in range(1, max_retries + 1):
            try:
                # Bump temperature on retries only - if attempt 1 fails (e.g. the model
                # produced unparseable JSON, like unescaped quotes inside a string value),
                # retrying at the SAME temperature (especially 0.0/greedy) just reproduces
                # the identical broken output every time. A small bump gives each retry an
                # actual chance at a different, hopefully valid, generation.
                attempt_temperature = min(temperature + 0.15 * (attempt - 1), 0.4)
                response = _do_call(
                    client, model, text, target_lang, source_lang_override, attempt_temperature,
                    disable_thinking=strategy["disable_thinking"],
                    tool_choice_none=strategy["tool_choice_none"],
                )
                choice = response.choices[0]
                message = choice.message
                raw_content = message.content or ""
                parsed = extract_json(raw_content)

                # Fallback: some vLLM builds still put a usable JSON blob inside
                # the "reasoning" field even when content is empty.
                if parsed is None:
                    reasoning_text = getattr(message, "reasoning", None) or ""
                    parsed = extract_json(reasoning_text)

                # Fallback: some builds route the JSON into a tool_call
                # structure instead of the message content. Try to extract
                # JSON from there as well.
                if parsed is None:
                    tool_call = getattr(message, "tool_call", None) or getattr(message, "tool_call", None)
                    if tool_call:
                        # tool_call.arguments is commonly a string containing the JSON
                        args = None
                        if hasattr(tool_call, "arguments"):
                            args = getattr(tool_call, "arguments")
                        elif isinstance(tool_call, dict):
                            args = tool_call.get("arguments") or tool_call.get("content")
                        if isinstance(args, str) and args.strip():
                            parsed = extract_json(args)

                # If we still couldn't parse JSON, log full response for debugging
                if parsed is None:
                    try:
                        logger.info("Full response (repr): %r", response)
                    except Exception:
                        logger.info("Full response choice for debugging: %s", getattr(choice, "__dict__", choice))

                # Also try top-level choice.tool_call (some servers put tool_call there)
                if parsed is None:
                    top_tool_call = getattr(choice, "tool_call", None)
                    if top_tool_call:
                        args = None
                        if hasattr(top_tool_call, "arguments"):
                            args = getattr(top_tool_call, "arguments")
                        elif isinstance(top_tool_call, dict):
                            args = top_tool_call.get("arguments") or top_tool_call.get("content")
                        if isinstance(args, str) and args.strip():
                            parsed = extract_json(args)

                if parsed is None:
                    raise ValueError(
                        f"Could not parse JSON (finish_reason={choice.finish_reason}, "
                        f"strategy={strategy}): content={raw_content[:200]!r}"
                    )

                parsed.setdefault("mixed_components", [])
                if source_lang_override:
                    parsed["detected_language"] = source_lang_override
                return parsed

            except Exception as e:  # noqa: BLE001 - retry on any transient failure
                last_err = e
                logger.warning(
                    "Strategy %s attempt %d/%d failed: %s", strategy, attempt, max_retries, e
                )
                time.sleep(1.2 * attempt)
        # move on to next strategy after exhausting retries for this one
        logger.info("Moving to next strategy after exhausting retries for %s", strategy)

    logger.error("All strategies/retries exhausted for text: %r - %s", text[:80], last_err)
    # Final fallback: attempt a plain translation (no JSON) so we at least
    # recover a translated_text even when the structured JSON response fails.
    try:
        logger.info("Attempting plain-text translation fallback for text: %.60s", text)
        fb_kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": f"You are a translator. Translate the following text to {target_lang}. Reply only with the translation, no extra text."},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        fb_resp = client.chat.completions.create(**fb_kwargs)
        fb_choice = fb_resp.choices[0]
        fb_msg = fb_choice.message
        fb_text = (getattr(fb_msg, "content", None) or "").strip()
        if not fb_text:
            # last resort: try reasoning field or tool_call args
            fb_text = (getattr(fb_msg, "reasoning", None) or "").strip()
        if fb_text:
            return {
                "detected_language": source_lang_override or "unknown",
                "detected_language_name": "unknown",
                "script_type": "unknown",
                "mixed_components": [],
                "translated_text": fb_text,
                "warning": "Used plain-text fallback because structured JSON parsing failed",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("Plain-text fallback also failed: %s", e)

    return {
        "detected_language": source_lang_override or "unknown",
        "detected_language_name": "unknown",
        "script_type": "unknown",
        "mixed_components": [],
        "translated_text": None,
        "error": str(last_err),
    }


# --------------------------------------------------------------------------- #
# Record-level translation (preserves all original fields)
# --------------------------------------------------------------------------- #
def translate_record(
    client: OpenAI,
    model: str,
    record: Dict[str, Any],
    target_lang: str,
    source_lang_hint: Optional[str] = None,
    text_field: str = "text",
) -> Dict[str, Any]:
    text = record.get(text_field, "")
    result = call_model(client, model, text, target_lang, source_lang_override=source_lang_hint)

    enriched = dict(record)
    enriched["detected_language"] = result.get("detected_language")
    enriched["detected_language_name"] = result.get("detected_language_name")
    enriched["script_type"] = result.get("script_type")
    enriched["mixed_components"] = result.get("mixed_components", [])
    enriched[f"{text_field}_translated"] = result.get("translated_text")
    if "error" in result:
        enriched["translation_error"] = result["error"]
    return enriched


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #
def load_records(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass
    records = []
    for line in raw.splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        records.append(json.loads(line))
    return records


def save_records(records: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("Wrote %d translated records to %s", len(records), path)


def process_records(
    records: List[Dict[str, Any]],
    client: OpenAI,
    model: str,
    target_lang: str,
    source_lang_hint: Optional[str] = None,
    text_field: str = "text",
    workers: int = 4,
) -> List[Dict[str, Any]]:
    results: List[Optional[Dict[str, Any]]] = [None] * len(records)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(translate_record, client, model, rec, target_lang, source_lang_hint, text_field): i
            for i, rec in enumerate(records)
        }
        for fut in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.error("Record %d failed entirely: %s", idx, e)
                results[idx] = {**records[idx], "translation_error": str(e)}
    return results  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Demo records
# --------------------------------------------------------------------------- #
DEMO_RECORDS = [
    {"message_id": "mni_001", "language": "mni", "text": "মসি ওইদুনসু, ফ্রেঞ্চ ঙাংবা বেলজিয়নশিং অমসুং স্বিসশিংনা স্কুলদা স্তেন্দর্দ ওইবা ফ্রেঞ্চ তম্মী, অদুনা অদোম্না করিগুম্বা স্তেন্দর্দ ফ্রেঞ্চকী মশিং থিবগী পথাপ অদু শিজিন্নরবসু মখোয়না লৌশিনবা অদুমক ঙমগনি।"},
    {"message_id": "mni_007", "language": "mni", "text": "সহর অদুগী অতোপ্পা লম্বেল ওইরিবা বেল্তৱেদা চাউনা ত্রাফিক্তা থেংথহনখিবগী পাউদম লৈখিদে।"},
    {"message_id": 1, "language": "hi", "text": "aj PM Modi ne BRICS summit me participate kiya"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate JSON records with a locally served Gemma model.")
    parser.add_argument("--input", help="Path to input JSON/JSONL file")
    parser.add_argument("--output", default="translated_output.json")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument("--source-lang", default=None, help="Optional manual override, e.g. hi, ta, ar")
    parser.add_argument("--text-field", default="text")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    if args.demo:
        records = DEMO_RECORDS
    elif args.input:
        records = load_records(args.input)
    else:
        parser.error("Provide --input <file> or use --demo")
        return

    start = time.time()
    translated = process_records(
        records, client=client, model=args.model, target_lang=args.target_lang,
        source_lang_hint=args.source_lang, text_field=args.text_field, workers=args.workers,
    )
    logger.info("Translated %d records in %.1fs", len(translated), time.time() - start)
    save_records(translated, args.output)
    print(json.dumps(translated, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()