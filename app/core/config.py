"""
Central configuration for the translation service.
All tunables (timeouts, cache TTL, model paths) live here or in configs/models.yaml.
"""
from pathlib import Path
from functools import lru_cache
import yaml
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LANGUAGE_MODELS_CONFIG_PATH = BASE_DIR / "configs" / "language_models.yaml"
NODE_SCRIPT_PATH = BASE_DIR / "node_backend" / "translate_darinrowe.js"


class Settings(BaseSettings):
    # Redis cache
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 60 * 60 * 24  # 1 day
    cache_enabled: bool = True

    # Googletrans - unofficial scraper via a Node.js subprocess (node_backend/).
    # Kept short: a slow/hanging response here should fail fast into the next
    # model in the chain rather than tie up a request waiting on it.
    googletrans_timeout_s: float = 6.0

    # Gemma fallback model - served locally via sglang's OpenAI-compatible API
    gemma_base_url: str = "http://localhost:30004/v1"
    gemma_model_name: str = "gemma-4-26b-a4b-it"
    gemma_api_key: str = "not-needed"
    # Each retry inside gemma_engine.call_model() is its own HTTP request to
    # Gemma. Confirmed live: if Gemma doesn't cancel generation the instant a
    # client gives up (its own server-side behavior, outside this repo), an
    # abandoned retry can keep running there anyway - so one busy semaphore
    # slot on our side (see gemma_max_concurrent_requests below) could still
    # cause several concurrent requests on Gemma's side under load (we
    # measured our 8-slot cap corresponding to ~21 actually running on
    # Gemma's own metrics). Kept low to bound how many phantom requests one
    # struggling translation can generate.
    gemma_max_retries: int = 1
    # wall-clock cap enforced by our async wrapper. Deliberately close to (not
    # longer than) known downstream client timeouts - one pipeline consumer's
    # own read timeout was raised from 40s to 60s alongside this value, to
    # give long documents (multi-paragraph digest posts in languages with no
    # fallback model, e.g. Russian/Chinese) more room to finish instead of
    # being cut off mid-retry, at the cost of holding a concurrency slot
    # longer per request under heavy load. If we held resources longer than a
    # caller is even still listening, that's pure waste that compounds under
    # retries. Must stay ABOVE gemma_client_timeout_s below (see that field's
    # comment for why the ordering matters).
    gemma_timeout_s: float = 60.0
    gemma_verify_timeout_s: float = 12.0  # cap for the best-effort entity-check follow-up call
    gemma_repair_timeout_s: float = 12.0  # cap for the best-effort entity-repair follow-up call
    # Entity verify/repair (see app/models/gemma_model.py) adds up to 2 extra
    # Gemma calls per translation, unconditionally (verify runs on every
    # non-empty translation; repair only when verify finds something). Under
    # sustained heavy pipeline load this is a meaningful chunk of Gemma's
    # total demand for a quality check that's explicitly best-effort, not
    # required. Disabled here while GPU capacity is tight - set to true (or
    # TRANSLATE_GEMMA_ENABLE_ENTITY_VERIFICATION=true) to re-enable.
    gemma_enable_entity_verification: bool = False
    # Long inputs are split into sentence-aware chunks of at most this many
    # characters (see app/models/reference/gemma_engine.py:split_text_for_translation)
    # and translated as several small, fast calls instead of one large call
    # gambling on finishing before gemma_timeout_s. Confirmed real case this
    # fixes: 2500-3500 token Telegram/Facebook digest posts consistently
    # timing out as a single request under load. Character-based (not
    # word-based) so it works correctly for CJK scripts with no spaces
    # between words. ~1800 chars is roughly 300-350 English words - small
    # enough to reliably finish in a few seconds even under GPU contention.
    gemma_chunk_max_chars: int = 1800
    # The underlying HTTP client's own per-call timeout (app/models/gemma_model.py).
    # Must be COMFORTABLY SHORTER than gemma_timeout_s/verify/repair above -
    # otherwise an abandoned call keeps running in the background (Python
    # can't cancel a blocking thread) long after we've already told the
    # caller it failed, leaking a Gemma slot the whole time. Confirmed live
    # this caused Gemma's concurrent-request count to climb and never
    # recover under sustained retries.
    gemma_client_timeout_s: float = 10.0
    # Caps how many Gemma calls (translate + verify + repair combined) this
    # process will have in flight at once. Confirmed live: Gemma's own server
    # (sglang, --max-running-requests 40) can be pushed into universal
    # timeouts and even trip our circuit breaker when too many large
    # (2000+ token) requests run concurrently - this keeps our own demand on
    # it well below that ceiling regardless of how many /translate requests
    # arrive at once.
    gemma_max_concurrent_requests: int = 5

    # Qwen3-VL-8B - planned local vLLM service; host it on port 8029.
    # Port 8001 is already used by another service on the current host.
    qwen_base_url: str = "http://localhost:8029/v1"
    qwen_model_name: str = "qwen3-vl-8b"
    qwen_api_key: str = "not-needed"
    qwen_timeout_s: float = 15.0

    # IndicTrans2 microservice (see indictrans_server/) - HTTP call, not in-process.
    # One /translate call now covers the WHOLE input text - indictrans_server
    # does its own chunking and batches up to 16 chunks per generate() call,
    # so a long document may take several batches; sized accordingly rather
    # than for a single small chunk.
    indictrans_service_url: str = "http://localhost:8200"
    indictrans_timeout_s: float = 90.0
    
    # Circuit breaker
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_cooldown_s: float = 30.0

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8048
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_prefix = "TRANSLATE_"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_language_routing_config() -> dict:
    """Loads configs/language_models.yaml - the per-source-language fallback
    chains (e.g. hi -> [gemma, indictrans2])."""
    with open(LANGUAGE_MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
