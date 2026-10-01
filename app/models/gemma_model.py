"""
Wraps app/models/reference/gemma_engine.py (the user's tested gemma.py) behind
BaseTranslator. This is the universal fallback/default model:
  - the only model tried for any language not in configs/language_models.yaml
  - used directly for romanized/mixed-script text, since gemma_engine.py's
    own prompt already classifies script_type as native / romanized / mixed /
    latin_native and translates accordingly.

call_model() in gemma_engine.py is a SYNCHRONOUS function that can internally
sleep/retry across up to 3 strategies x max_retries attempts. We must never
call it directly from an async route - it would block the entire event loop
and stall every other in-flight request. So we run it in a worker thread via
asyncio.to_thread, and enforce an outer wall-clock timeout on top of it.
"""
import asyncio
import logging

from openai import OpenAI

from app.core.cache import cache, make_chunk_cache_key
from app.core.config import get_settings
from app.models.base import BaseTranslator, TranslationResult
from app.models.reference import gemma_engine
from app.utils.burmese_normalizer import prepare_for_translation
from app.utils.lang_codes import normalize_language_code

logger = logging.getLogger("translation_service.models.gemma")


class _NullAsyncContext:
    """No-op async context manager - lets health_check() skip the semaphore
    without duplicating the call logic in translate()."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


_NULL_CONTEXT = _NullAsyncContext()


class GemmaModel(BaseTranslator):
    def __init__(
        self,
        name: str = "gemma",
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
    ):
        self.name = name
        self._settings = get_settings()
        # One shared OpenAI client (thin HTTP wrapper) reused across requests -
        # avoids reconnect overhead on every call.
        self._client = OpenAI(
            base_url=base_url or self._settings.gemma_base_url,
            api_key=api_key or self._settings.gemma_api_key,
            # Must be COMFORTABLY SHORTER than gemma_timeout_s/verify/repair in
            # config.py (previously this was 100.0 - LONGER than all of them,
            # e.g. > the 60s outer wall-clock cap). That was a real bug, not
            # just a redundant safety margin: when our outer asyncio.wait_for()
            # gives up, it cannot actually stop the underlying thread (Python
            # threads aren't forcibly cancellable) - the blocking HTTP call
            # inside it just kept running for up to 100s in the background,
            # still occupying a slot on Gemma's server, even though we'd
            # already told the caller it failed. Confirmed live: this caused
            # Gemma's concurrent-request count to climb and never fully
            # recover under sustained retries, since every abandoned call kept
            # consuming capacity long after we stopped waiting on it. Setting
            # this shorter than every outer cap means an abandoned call times
            # out (and releases its slot) at roughly the same time we give up
            # on it, instead of up to 40+ seconds later. See config.py's
            # gemma_client_timeout_s comment for the current value/reasoning.
            timeout=self._settings.gemma_client_timeout_s,
            max_retries=0,
        )
        self._model_name = model_name or self._settings.gemma_model_name
        # Shared across every translate() call this process handles - bounds
        # total concurrent Gemma calls (translate + verify + repair combined)
        # regardless of how many /translate requests arrive at once. See
        # Settings.gemma_max_concurrent_requests.
        self._semaphore = asyncio.Semaphore(self._settings.gemma_max_concurrent_requests)

    async def translate(
        self, text: str, source_lang: str, target_lang: str, verify: bool | None = None,
        _use_semaphore: bool = True, _use_cache: bool = True,
    ) -> TranslationResult:
        # translator_pipeline.py calls translate() generically for any model
        # and never passes `verify` (that kwarg is Gemma-specific) - so the
        # default here is driven by Settings.gemma_enable_entity_verification
        # instead of a hardcoded True, letting it be toggled without touching
        # the pipeline or breaking other models' translate() signatures.
        # health_check() explicitly passes verify=False regardless of this
        # setting - a health check should never trigger it.
        if verify is None:
            verify = self._settings.gemma_enable_entity_verification

        source_hint = None if source_lang in ("auto", "", None) else source_lang

        text = prepare_for_translation(text)

        # health_check() passes _use_semaphore=False: it must never compete
        # with real translation traffic for one of the gemma_max_concurrent_requests
        # slots. Confirmed live: under real load with all slots busy (which is
        # the concurrency cap working as intended, not a failure), the health
        # check couldn't get a turn within its 5s budget (registry.py) and
        # reported Gemma as "down" in the UI even though a direct call to
        # Gemma succeeded in well under a second. A health check needs an
        # honest, immediate answer regardless of how busy real work is.
        semaphore_cm = self._semaphore if _use_semaphore else _NULL_CONTEXT

        async def _call_chunk(chunk_text: str):
            # Cached independently per chunk, separate from the whole-document
            # cache in translator_pipeline.py. Confirmed real case this helps:
            # recurring boilerplate (e.g. a Telegram channel's identical post
            # intro/tagline reused across many otherwise-unique posts) becomes
            # a cache hit after the first time, instead of every document
            # needing a fresh Gemma call just because the document AS A WHOLE
            # is unique even when large pieces of it aren't. Keyed on the
            # resolved source_hint (not the raw source_lang, which may be
            # "auto") so a hit only ever reuses a result Gemma produced for
            # the same effective language.
            # _use_cache=False for health_check(): the cache TTL is 24h, so a
            # cached success would mask a genuine Gemma outage as "healthy"
            # for up to a full day instead of ever re-checking for real.
            chunk_cache_key = make_chunk_cache_key(chunk_text, source_hint or "auto", target_lang)
            cached = await cache.get(chunk_cache_key) if _use_cache else None
            if cached is not None:
                return cached

            async def _do():
                async with semaphore_cm:
                    return await asyncio.to_thread(
                        gemma_engine.call_model,
                        self._client,
                        self._model_name,
                        chunk_text,
                        target_lang,
                        source_hint,
                        self._settings.gemma_max_retries,
                    )

            try:
                # wait_for wraps the semaphore acquisition too, not just the
                # call itself - otherwise time spent queued for a slot
                # doesn't count against gemma_timeout_s, so a caller could
                # still be kept waiting well past their own timeout (queue
                # wait + call time) even though our "cap" was technically
                # respected the whole time. Confirmed live: this was still
                # happening after tightening the timeouts, because queueing
                # time was invisible to the old cap.
                chunk_result = await asyncio.wait_for(_do(), timeout=self._settings.gemma_timeout_s)
            except asyncio.TimeoutError:
                raise TimeoutError("gemma call exceeded wall-clock timeout")

            # Only cache genuine successes - never a result carrying an error.
            if chunk_result.get("translated_text") and not chunk_result.get("error"):
                await cache.set(chunk_cache_key, {
                    "translated_text": chunk_result.get("translated_text"),
                    "detected_language": chunk_result.get("detected_language"),
                    "mixed_components": chunk_result.get("mixed_components", []),
                })
            return chunk_result

        # Long documents (confirmed real case: 2500-3500 token Telegram/
        # Facebook digest posts) are split into sentence-aware chunks here
        # and translated as several small, fast calls instead of one large
        # call gambling on finishing before gemma_timeout_s. Short inputs
        # (the common case) come back as a single chunk, so this is
        # identical to one direct call for everything but long documents.
        #
        # Chunks run CONCURRENTLY (unlike IndicTrans2's chunking, which is
        # sequential) - safe here because Gemma is served by sglang, which
        # is built for concurrent request handling (continuous batching),
        # unlike IndicTrans2's unlocked single-model server where concurrent
        # calls caused real corruption/hangs. It also doesn't add load
        # beyond what's already budgeted: self._semaphore caps TOTAL
        # concurrent Gemma calls process-wide regardless of whether those
        # slots are filled by one document's chunks or several different
        # requests, so this doesn't bypass gemma_max_concurrent_requests.
        # The real benefit: a multi-chunk document now takes roughly as long
        # as its SLOWEST chunk instead of the SUM of all chunks, directly
        # reducing the chance of exceeding gemma_timeout_s for the request
        # as a whole.
        chunks = gemma_engine.split_text_for_translation(text, max_chars=self._settings.gemma_chunk_max_chars)
        if not chunks:
            return TranslationResult(translated_text="", detected_language=source_lang)

        # asyncio.gather preserves result order matching input order
        # regardless of completion order, so reassembly below stays correct.
        # Tasks (not bare coroutines) so that if one chunk fails, we can
        # explicitly cancel the still-pending siblings instead of leaving
        # them running unsupervised in the background - cancelling frees
        # their semaphore slot immediately (via the `async with` releasing
        # on the propagated CancelledError) rather than making some other
        # queued request wait out that chunk's own full timeout for no
        # reason, now that we already know the overall translation failed.
        tasks = [asyncio.ensure_future(_call_chunk(chunk)) for chunk in chunks]
        try:
            chunk_results = await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                if not t.done():
                    t.cancel()
            raise

        pieces = []
        detected_language = None
        mixed_components = []
        for idx, chunk_result in enumerate(chunk_results):
            if chunk_result.get("error") and not chunk_result.get("translated_text"):
                raise RuntimeError(
                    f"gemma translation failed on chunk {idx + 1}/{len(chunks)}: {chunk_result['error']}"
                )
            if idx == 0:
                detected_language = chunk_result.get("detected_language")
                mixed_components = chunk_result.get("mixed_components", []) or []
            pieces.append(chunk_result.get("translated_text") or "")

        translated_text = " ".join(pieces)

        # Best-effort entity check + repair (see gemma_engine.py's comment above
        # VERIFY_SYSTEM_PROMPT for why this exists) - never allowed to fail or delay the
        # translation itself. Skipped for the trivial health-check call so routine polling
        # doesn't triple Gemma's load.
        entity_issues = []
        if verify and translated_text:
            async def _verify():
                async with self._semaphore:
                    return await asyncio.to_thread(
                        gemma_engine.verify_entities,
                        self._client,
                        self._model_name,
                        text,
                        translated_text,
                    )

            try:
                verify_result = await asyncio.wait_for(_verify(), timeout=self._settings.gemma_verify_timeout_s)
                entity_issues = verify_result.get("entity_issues", [])
            except Exception as e:
                logger.warning("Entity verification skipped (non-fatal): %s", e)

            if entity_issues:
                async def _repair():
                    async with self._semaphore:
                        return await asyncio.to_thread(
                            gemma_engine.repair_entities,
                            self._client,
                            self._model_name,
                            text,
                            translated_text,
                            entity_issues,
                        )

                try:
                    translated_text = await asyncio.wait_for(_repair(), timeout=self._settings.gemma_repair_timeout_s)
                except Exception as e:
                    logger.warning("Entity repair skipped (non-fatal): %s", e)

        return TranslationResult(
            translated_text=translated_text,
            detected_language=normalize_language_code(detected_language) if detected_language else None,
            corrected_text=None,
            pronunciation=None,
            entity_issues=entity_issues,
            mixed_components=[normalize_language_code(component) for component in mixed_components if component],
        )

    async def health_check(self) -> bool:
        try:
            result = await self.translate(
                "hello", "en", "en", verify=False, _use_semaphore=False, _use_cache=False
            )
            return bool(result.translated_text)
        except Exception:
            return False
