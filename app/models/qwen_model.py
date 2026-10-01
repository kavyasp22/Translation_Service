"""
Wraps the Qwen3-VL-8B-Instruct model already hosted via vLLM (per your docker
inspect: served-model-name 'qwen3-vl-8b'). Unlike Gemma, we don't need the
elaborate JSON-extraction/retry-strategy dance from gemma_engine.py - this is
a simple single-shot translation prompt. If you find Qwen's output needs
stricter parsing (e.g. it wraps answers in commentary), copy the
extract_json/strategy pattern from gemma_engine.py here too.

NOTE: your docker inspect showed this container as "exited" with no Ports
section visible. Start it and fill in TRANSLATE_QWEN_BASE_URL with the real
published port before this backend will work.
"""
import asyncio
import logging

from openai import OpenAI

from app.core.config import get_settings
from app.models.base import BaseTranslator, TranslationResult
from app.utils.lang_codes import normalize_language_code

logger = logging.getLogger("translation_service.models.qwen")

_SYSTEM_PROMPT = (
    "You are a careful multilingual translation engine. Translate the user's text into the requested target "
    "language. First, detect whether the input is native-script or romanized/transliterated text. For romanized "
    "inputs, reconstruct the intended native-script meaning before translating. This is especially important for "
    "Burmese, Pashto, Balochi, and Divehi. Do not assume Romanized Pashto/Balochi/Divehi are Urdu or Arabic "
    "just because they use Perso-Arabic-looking letters. Use the actual vocabulary and sentence patterns of each "
    "language. For Burmese, if the input is Romanized Burmese, normalize it to native Myanmar script before "
    "translation; for Pashto/Balochi/Divehi, normalize to the proper native script of that language before "
    "translation. Preserve meaningful English names and brand terms when they are part of the source, while "
    "translating the underlying language faithfully. Respond with ONLY the translated text - no explanations, "
    "no quotes, no additional commentary."
)


def _call_qwen_sync(client: OpenAI, model_name: str, text: str, target_lang: str) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Target language code: {target_lang}\n\nText:\n{text}"},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    return (response.choices[0].message.content or "").strip()


class QwenModel(BaseTranslator):
    name = "qwen"

    def __init__(self):
        self._settings = get_settings()
        self._client = OpenAI(
            base_url=self._settings.qwen_base_url,
            api_key=self._settings.qwen_api_key,
            timeout=10.0,
            max_retries=0,
        )

    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        try:
            translated = await asyncio.wait_for(
                asyncio.to_thread(
                    _call_qwen_sync, self._client, self._settings.qwen_model_name, text, target_lang
                ),
                timeout=self._settings.qwen_timeout_s,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("qwen call exceeded wall-clock timeout")

        if not translated:
            raise RuntimeError("qwen returned empty translation")

        return TranslationResult(
            translated_text=translated,
            detected_language=normalize_language_code(source_lang),
            mixed_components=[],
        )

    async def health_check(self) -> bool:
        try:
            result = await self.translate("hello", "en", "en")
            return bool(result.translated_text)
        except Exception:
            return False
