"""
Wraps the Node.js googletrans scraper (node_backend/translate_darinrowe.js) behind
BaseTranslator.

We use asyncio.create_subprocess_exec instead of subprocess.run so a slow/hanging
call doesn't block the whole FastAPI event loop (which would stall every other
in-flight request).

Reminder: this is an unofficial scraper. It can be rate-limited or IP-blocked
by Google at any time. Treat failures here as expected and let the fallback
chain handle them - don't increase timeouts to "fix" flakiness, that just
makes bad requests slower.
"""
import asyncio
import json
import logging

from app.core.config import get_settings, NODE_SCRIPT_PATH
from app.models.base import BaseTranslator, TranslationResult
from app.utils.lang_codes import normalize_language_code

logger = logging.getLogger("translation_service.models.googletrans")


class GoogletransModel(BaseTranslator):
    name = "googletrans"

    def __init__(self):
        self._settings = get_settings()

    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(NODE_SCRIPT_PATH),
            text,
            source_lang,
            target_lang,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._settings.googletrans_timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError("googletrans subprocess timed out")

        if proc.returncode != 0:
            raise RuntimeError(f"googletrans subprocess failed: {stderr.decode().strip()}")

        output = json.loads(stdout.decode().strip())
        if "error" in output:
            raise RuntimeError(f"googletrans error: {output['error']}")

        return TranslationResult(
            translated_text=output.get("translated_text", ""),
            detected_language=normalize_language_code(output.get("detected_language")),
            corrected_text=output.get("corrected_text") or None,
            pronunciation=output.get("pronunciation") or None,
            mixed_components=[],
        )

    async def health_check(self) -> bool:
        try:
            result = await self.translate("hello", "en", "en")
            return bool(result.translated_text)
        except Exception:
            return False
