"""
Calls the IndicTrans2 microservice (see indictrans_server/) over HTTP.

Why a separate microservice instead of loading the model in-process here:
  - IndicTrans2 needs `transformers` + `torch` + `IndicTransToolkit` and a GPU
    slot of its own - keeping it out of the main API process means the main
    service stays lightweight and doesn't need those heavy deps.
  - It's a different serving pattern (encoder-decoder generate() with custom
    pre/post-processing) than the OpenAI-compatible chat models, so isolating
    it behind its own HTTP contract keeps this file simple.

IMPORTANT LIMITATION: the checkpoint configured in indictrans_server
(ai4bharat/indictrans2-indic-en-1B) only translates INDIC -> ENGLISH. If
target_lang isn't English, this backend should not be in the routing chain
for that language pair - see configs/language_models.yaml.

CHUNKING/BATCHING: this file used to split long text into ~100-word pieces
and send each as a separate HTTP request (sequentially, then briefly
concurrently). Both approaches were wrong: sequential was slow (linear in
chunk count), and concurrent requests caused multiple simultaneous
`model.generate()` calls on the single shared model instance in
indictrans_server, which has no locking and could hang the whole
microservice under load - confirmed live, requiring a hard process restart.
indictrans_server/app.py already does its own sentence-aware chunking AND
batches up to 16 chunks per `generate()` call - safe (one call at a time)
and fast (real GPU batch parallelism, not concurrent Python requests). So
this file now just sends the whole text in a single request and lets the
server do the chunking/batching - no client-side splitting needed.
"""
import logging

import httpx

from app.core.config import get_settings
from app.models.base import BaseTranslator, TranslationResult
from app.utils.lang_codes import normalize_language_code

logger = logging.getLogger("translation_service.models.indictrans2")


import re


def _is_transliterated_output(text: str, source_lang: str) -> bool:
    if source_lang not in ("hi", "ur", "pa", "mr", "ne", "bn", "gu"):
        return False
    hinglish_markers = {
        "yaar", "yeh", "woh", "toh", "sachch", "mein", "hai", "bhi",
        "kya", "kar", "bhai", "raha", "rahi", "chahiye", "karna", "ho", "rahe"
    }
    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    matches = words.intersection(hinglish_markers)
    return len(matches) >= 2


class IndicTrans2Model(BaseTranslator):
    name = "indictrans2"

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=self._settings.indictrans_service_url,
            timeout=self._settings.indictrans_timeout_s,
        )

    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        if target_lang != "en":
            raise RuntimeError(
                "indictrans2 (indic-en-1B) only supports target_lang='en'"
            )

        source_lang = normalize_language_code(source_lang)

        if not text.strip():
            return TranslationResult(translated_text="", detected_language=source_lang)

        last_exc = None
        for attempt in range(2):
            try:
                resp = await self._client.post(
                    "/translate",
                    json={"text": text, "source_lang": source_lang, "target_lang": target_lang},
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"indictrans2 service error {resp.status_code}: {resp.text}")

                data = resp.json()
                translated = data.get("translated_text", "")
                if not translated:
                    raise RuntimeError("indictrans2 returned empty translation")

                if _is_transliterated_output(translated, source_lang):
                    raise RuntimeError(
                        f"indictrans2 produced transliterated romanized text instead of English translation: '{translated[:60]}...'"
                    )

                return TranslationResult(translated_text=translated, detected_language=source_lang)
            except Exception as e:
                last_exc = e

        raise RuntimeError(f"indictrans2 service unreachable: {last_exc}")

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False
