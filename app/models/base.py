from abc import ABC, abstractmethod
from typing import Optional


class TranslationResult:
    def __init__(
        self,
        translated_text: str,
        detected_language: Optional[str] = None,
        corrected_text: Optional[str] = None,
        pronunciation: Optional[str] = None,
        entity_issues: Optional[list] = None,
        mixed_components: Optional[list[str]] = None,
    ):
        self.translated_text = translated_text
        self.detected_language = detected_language
        self.corrected_text = corrected_text
        self.pronunciation = pronunciation
        self.mixed_components = mixed_components or []
        # Best-effort list of flagged named-entity mismatches (currently only
        # populated by GemmaModel - see gemma_engine.verify_entities). Empty
        # for backends that don't run this check.
        self.entity_issues = entity_issues or []


class BaseTranslator(ABC):
    """Every model backend (Gemma, IndicTrans2, Qwen, future additions) implements
    this same interface so the pipeline can call any of them interchangeably."""

    name: str = "base"

    @abstractmethod
    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        """Raise an exception on failure — the pipeline's fallback chain handles it."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
