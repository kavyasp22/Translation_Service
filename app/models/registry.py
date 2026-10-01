"""
Holds one long-lived instance per model backend. Created once at FastAPI
startup (see app/main.py) so we never re-instantiate an OpenAI/httpx client or
re-check anything per request - that per-request setup cost is exactly the
kind of thing that was likely hurting your original test script's latency.

Backends that need config you haven't filled in yet (Qwen port)
still get REGISTERED here - they just fail fast at
call time with a clear error, which the pipeline's fallback chain handles.
This means a missing API key never crashes startup, it just makes that one
backend unavailable until you configure it.
"""
import logging

from app.core.config import get_settings
from app.models.base import BaseTranslator
from app.models.googletrans_model import GoogletransModel
from app.models.gemma_model import GemmaModel
from app.models.qwen_model import QwenModel
from app.models.indictrans2_model import IndicTrans2Model

logger = logging.getLogger("translation_service.registry")


class ModelRegistry:
    def __init__(self):
        self._models: dict[str, BaseTranslator] = {}

    def load_all(self):
        logger.info("Loading model backends...")
        settings = get_settings()

        self._models["googletrans"] = GoogletransModel()
        self._models["gemma"] = GemmaModel(name="gemma")
        self._models["qwen"] = QwenModel()
        self._models["indictrans2"] = IndicTrans2Model()

        logger.info("Model backends loaded: %s", list(self._models.keys()))

    def get(self, name: str) -> BaseTranslator:
        return self._models[name]

    # async def health_snapshot(self) -> dict:
    #     results = {}
    #     for name, model in self._models.items():
    #         try:
    #             results[name] = await model.health_check()
    #         except Exception:
    #             results[name] = False
    #     return results
    async def health_snapshot(self) -> dict:
        import asyncio

        async def _check(name, model):
            try:
                return name, await asyncio.wait_for(model.health_check(), timeout=5.0)
            except Exception:
                return name, False

        pairs = await asyncio.gather(*(_check(n, m) for n, m in self._models.items()))
        return dict(pairs)


registry = ModelRegistry()
