# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A translation-as-a-service API (`app/`, FastAPI) that routes each request across
multiple translation backends with per-language fallback chains, fronted by a
Redis cache and a circuit breaker. `frontend/` is a React console for
exercising it manually. `indictrans_server/` is a separate microservice (own
GPU, own dependency stack) for the IndicTrans2 model. This is not a git
repository (no `.git` directory) — there is no git history to consult.

Four model backends exist in this project: `gemma`, `qwen`, `indictrans2`,
and `googletrans` (an unofficial scraper called via a Node.js subprocess,
`node_backend/translate_darinrowe.js` — Node.js must be installed wherever
this runs, see `deployment/Dockerfile`). Sarvam Translate was removed
entirely — don't reintroduce references to it without re-adding the actual
integration.

## Commands

```bash
# Backend
pip install -r requirements.txt
cd node_backend && npm install && cd ..   # needed for the googletrans backend
redis-server &                       # or set TRANSLATE_CACHE_ENABLED=false
uvicorn app.main:app --reload        # dev server, http://localhost:8000

# IndicTrans2 microservice (separate GPU host/venv; not needed for basic dev)
cd indictrans_server && pip install -r requirements.txt && python app.py   # :8100

# Frontend
cd frontend && npm install && npm run dev    # http://localhost:5173
cd frontend && npm run build                 # production build -> dist/

# Smoke test (requires the backend running on :8000)
python tests/smoke_test.py

# Check which backends are actually live (missing keys/unstarted containers show up here)
curl http://localhost:8000/health
```

`deployment/` has a Dockerfile + docker-compose for containerized deploys; see
`DEPLOYMENT.md` for a full bare-metal/systemd walkthrough (server prereqs,
starting the Qwen/IndicTrans2 containers, nginx reverse proxy, systemd units).

There is no automated test suite, linter, or type checker configured —
`tests/smoke_test.py` is a manual script that posts a few sample inputs and
prints the routing decision for eyeballing, not a pytest suite with
assertions. Don't assume `pytest`, `ruff`, `mypy`, etc. are available.

## Architecture

### Request flow

`app/api/routes.py` → `app/pipeline/translator_pipeline.py` (`translate()`) is
the single orchestration point:

1. Check the Redis cache (`app/core/cache.py`) keyed by
   `sha256(source_lang:target_lang:text)`.
2. Get a routing decision from `app/pipeline/language_router.py` — an ordered
   list of model names to try (the "chain").
3. Walk the chain in order via `app/models/registry.py`. Each attempt is
   guarded by the circuit breaker (`app/pipeline/circuit_breaker.py`); on
   failure it moves to the next model in the chain and records a fallback
   reason. The first success is cached and returned.
4. If every model in the chain fails, the pipeline raises and the route
   returns HTTP 502.

### Routing logic — two modes, in `app/pipeline/language_router.py`

1. **Language-specific**: if the detected/declared source language has an
   entry in `configs/language_models.yaml`, that exact fallback chain is used
   verbatim (e.g. `hi: [gemma, indictrans2]`). This is where deliberate
   per-language model choices live — edit the YAML, not the router, to change
   a language's chain.
2. **Generic fallback**: for any language not in that table,
   `app/utils/script_detect.py` classifies the text by Unicode script range
   (native vs. Latin) and langid confidence, and `language_router.py` uses
   that to choose the order of `gemma`/`googletrans`: native script with high
   detection confidence tries Googletrans first (free, but an unofficial
   scraper that can be rate-limited or IP-blocked at any time); low-
   confidence native script goes to Gemma first instead (Googletrans is
   still available there as a fallback). **Googletrans is never used at all
   for romanized/mixed-script text** (`script_type == "latin"`) — dropped
   from the candidate chain outright, in both routing modes, even when a
   manual `source_lang` override names a language that normally has
   Googletrans in its chain. Confirmed on real examples (romanized Burmese)
   that it does noticeably worse than Gemma there, often misdetecting the
   language entirely — this isn't a de-prioritization, it's a hard
   exclusion. The same `script_type`/`route_reason` metadata is also still
   used to promote Gemma to the front of a language-specific chain when the
   input is romanized.

When adding a new language to the fallback-chain table, edit
`configs/language_models.yaml` — it's hot-loaded via `get_language_routing_config()`
in `app/core/config.py` (`@lru_cache`, so a running process won't pick up
changes without a restart).

### Model backends (`app/models/`)

All backends implement `BaseTranslator` (`app/models/base.py`): async
`translate(text, source_lang, target_lang) -> TranslationResult`, raising on
failure (never returning an error sentinel) so the pipeline's fallback logic
can catch it uniformly, plus `health_check()`. `app/models/registry.py`
instantiates every backend once at FastAPI startup — misconfigured backends
(missing API key, unset port) still register successfully and just fail fast
at call time, so a missing credential never crashes startup, it only takes
that one backend out of rotation until configured.

- **`gemma`** — vLLM-served Gemma via OpenAI-compatible API. Wraps the
  synchronous `app/models/reference/gemma_engine.py` (a standalone
  detect+translate engine with its own retry/JSON-extraction strategies) via
  `asyncio.to_thread` + an outer wall-clock timeout, since that engine can
  block for multiple retries and must never run on the event loop directly.
  Universal fallback for nearly every language.
- **`qwen`** — Qwen3-VL-8B via vLLM, simple single-shot prompt (no retry
  dance like Gemma's). Config points at a placeholder port until the real
  container is running.
- **`indictrans2`** — HTTP call to the separate `indictrans_server/`
  microservice. **Indic → English only** — hard-enforced in code
  (`target_lang != "en"` raises immediately, no network call) as well as in
  the YAML config; the two must stay in sync if this ever changes.
- **`googletrans`** — unofficial Google Translate scraper, invoked as a Node.js
  subprocess (`node_backend/translate_darinrowe.js`) via
  `asyncio.create_subprocess_exec` so a slow/hanging call can't block the
  event loop. Free but unofficial — expect occasional rate-limiting/IP-block
  failures as normal, handled by the fallback chain; don't raise
  `googletrans_timeout_s` to paper over that.

Language-code translation between backends (ISO-ish internal codes ↔
IndicTrans2's FLORES-200 codes) is centralized in `app/utils/lang_codes.py`
— add new language mappings there, not inline in a model file.

### Config

Everything tunable is a `Settings` field in `app/core/config.py`, sourced from
env vars prefixed `TRANSLATE_` (or a `.env` file). Per-language fallback
chains are the exception — those live in `configs/language_models.yaml`, not
in `Settings`.

### Known, intentional limitations

- `langid` has no Manipuri class, so Meitei-in-Bengali-script text is
  classified as Bengali and gets Bengali's chain (`indictrans2 → gemma`),
  not Manipuri's (`gemma` alone). Confirmed via a live test this is not
  benign — IndicTrans2 doesn't actually understand Manipuri and produces a
  garbled result, not just "a different but working backend." Native
  Meetei Mayek script (Unicode U+ABC0–U+ABFF) is detected correctly and
  unaffected; only the Bengali-script case is a problem. See README.md's
  Known Limitations for the full test results.
- Native Myanmar-script text had the same class of problem — `langid`
  misclassified it as Chinese (`zh`) almost every time, silently routing it
  through Chinese's fallback chain. Unlike Manipuri, this one is fixed:
  Myanmar's Unicode block is now in the script-priority-override table in
  `app/utils/script_detect.py` (same mechanism already used for Punjabi/
  Gujarati/Odia/Tamil/Telugu/Kannada/Malayalam/Manipuri), so native Myanmar
  script is force-resolved to `my` regardless of what `langid` guesses. See
  README.md's Known Limitations for the full test results.
- `indictrans2` only ever outputs English; any non-English target skips it
  automatically.
- `qwen` and `indictrans2` require infrastructure (a running container /
  separate GPU service) that may not be up — until it is, those chains just
  fall through to the next model.
