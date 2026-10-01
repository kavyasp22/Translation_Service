# Translation Service

A translation-as-a-service API with automatic routing across multiple models,
plus a React console for testing it.

## Live deployment

Currently running via Docker Compose (`deployment/docker-compose.yml`) on
this machine, reachable both locally and over the LAN:

| Service | URL |
|---|---|
| Frontend UI | http://10.10.116.215:9045 (or http://localhost:9045 on this machine) |
| Backend API | http://10.10.116.215:8048 (or http://localhost:8048 on this machine) — docs at `/docs`, health at `/health` |
| IndicTrans2 microservice | http://localhost:8200 (host-only, not exposed on the LAN; the backend reaches it via `host.docker.internal:8200`) |

These are the actual ports published in `docker-compose.yml`
(`8048:8048`, `9045:9045`) bound to all interfaces — anyone on the same
network can reach them at the LAN URLs above. This is separate from the
"Run locally" section further down, which covers running the services
directly with `uvicorn`/`npm run dev` outside Docker (different, standard
dev ports: `:8000` and `:5173`).

```
translation_service/
├── app/                 # FastAPI backend (the actual service)
├── frontend/             # React testing console
├── indictrans_server/    # Separate microservice for IndicTrans2 (runs on GPU host)
├── configs/                # Language → model fallback chains
├── deployment/              # Dockerfile + docker-compose
└── tests/                    # Smoke test
```

## Model backends

| Backend | What it is | Notes |
|---|---|---|
| `gemma` | Your vLLM-served Gemma (26B), via `gemma.py` | Universal fallback for everything — tried for any language not in `configs/language_models.yaml` |
| `qwen` | Qwen3-VL-8B-Instruct, planned local vLLM service | **Not hosted yet** — host it on port `8029` and use `TRANSLATE_QWEN_BASE_URL=http://localhost:8029/v1` |
| `indictrans2` | `ai4bharat/indictrans2-indic-en-1B`, own microservice | **Indic → English only**; runs as its own process on port 8200 (own venv under `indictrans_server/venv`, GPU-hosted) — see `indictrans_server/README.md` |
| `googletrans` | Unofficial Google Translate scraper, via a Node.js subprocess (`node_backend/translate_darinrowe.js`) | Free but unofficial — expect occasional rate-limiting/IP-block failures as normal, not a bug; the fallback chain absorbs those |

## How routing works

1. `app/pipeline/language_router.py` checks `configs/language_models.yaml` for
   the detected (or user-declared) source language. If it's in the table,
   that exact chain is used. `configs/language_models.yaml` is the
   authoritative, always-current source — edit it directly to change a
   language's chain. Snapshot as of this writing:

   | Language | Chain |
   |---|---|
   | Chinese (`zh`) | gemma → googletrans → qwen |
   | Hindi (`hi`) | indictrans2 → googletrans → gemma |
   | Manipuri (`mni`) | gemma → indictrans2 |
   | Punjabi (`pa`) | gemma → indictrans2 → qwen → googletrans |
   | Assamese (`as`) | gemma → indictrans2 → googletrans |
   | Bengali (`bn`) | indictrans2 → gemma → googletrans |
   | Nepali (`ne`) | indictrans2 → gemma → googletrans |
   | Arabic (`ar`) | gemma → qwen → googletrans |
   | Urdu (`ur`) | gemma → googletrans → indictrans2 |
   | Pashto (`ps`) | gemma → googletrans |
   | Baluchi (`bal`) | gemma → qwen → googletrans |
   | Divehi (`dv`) | gemma → googletrans |
   | Malayalam (`ml`) | gemma → indictrans2 |

2. If the language isn't in that table, `app/utils/script_detect.py`
   classifies script type and language-detection confidence, and
   `language_router.py` uses that to choose between `googletrans` and
   `gemma`: native script with high detection confidence tries Googletrans
   first; anything else (low-confidence native script, romanized/mixed text,
   or a manual `source_lang` override) goes to Gemma first. The same
   metadata is also used to promote Gemma to the front of a
   language-specific chain on romanized text.
3. Every model call is wrapped by a **circuit breaker** (3 failures → skip
   for 30s) and the whole pipeline is fronted by a **Redis cache**.

## Known limitations (be aware of these, not hidden)

- **Sarvam Translate has been removed from this project entirely** (model
  backend, config settings, language-code mapping, and every chain that
  referenced it) — Gemma, IndicTrans2, Qwen, and Googletrans are the four
  models in the project now. Don't reintroduce Sarvam references without
  re-adding the actual integration.
- **Googletrans is back** (`app/models/googletrans_model.py`, calling
  `node_backend/translate_darinrowe.js` as a Node.js subprocess) — it's an
  unofficial scraper, so treat rate-limiting/IP-block failures as expected
  and let the fallback chain absorb them, not as something to "fix" by
  raising `googletrans_timeout_s`. Deploying this needs Node.js on the host
  (or in the container — see `deployment/Dockerfile`), not just Python.
- **Manipuri (`mni`) routing depends on how the language gets identified, not
  on whether `source_lang` is explicit vs. auto.** The configured chain is
  just `gemma` (single-model, no fallback), and that's used identically
  either way, *once the request resolves to `mni`*. Tested directly against
  the running API:
  - Explicit `source_lang: "mni"` → resolves to `mni` → `gemma`.
  - Auto-detect on **native Meetei Mayek script** (Unicode block
    U+ABC0–U+ABFF) → correctly resolves to `mni` → same chain, `gemma`.
  - Auto-detect on **Meitei written in Bengali script** → **misdetected as
    Bengali (`bn`)**, because langid has no Manipuri class. This is the one
    real gap: it silently falls into Bengali's chain (`indictrans2 →
    gemma`) instead of Manipuri's. IndicTrans2 doesn't actually understand
    Manipuri, and confirmed via a live test, this produces a garbled, wrong
    result — not a "still works, just different backend" situation as
    previously assumed here. If your users type Manipuri in Bengali script,
    have them explicitly select "Manipuri" as the source language rather
    than relying on auto-detect. A dedicated LID model would fix this at the
    detection layer if it matters enough to invest in.
- **IndicTrans2 only outputs English.** Any request with `target_lang != "en"`
  skips it automatically (enforced in code, not just config).
- **Qwen still needs to be hosted.** The planned vLLM endpoint is port `8029`;
  until the service is running there, `qwen` chains fail through to the next
  model. Port `8001` is already occupied on the current host. (IndicTrans2 is
  running as its own process on port `8200`.)
- **Burmese (`my`) has its own explicit chain: `[gemma, googletrans]`.**
  `langid` (used for auto-detect) misclassified native Myanmar-script text as
  Chinese (`zh`) essentially every time we tested it - since `zh` has its own
  entry, an unpinned Burmese input would silently take Chinese's chain
  instead of a real per-language decision, and only translated correctly by
  luck (Gemma happens to be first in `zh`'s chain too). Fixing the YAML entry
  alone wasn't enough, because the language code never actually resolved to
  `my` in the first place - the real fix is in `app/utils/script_detect.py`:
  Myanmar's Unicode block (U+1000–U+109F) is now in the same
  script-priority-override table already used for Punjabi/Gujarati/Odia/
  Tamil/Telugu/Kannada/Malayalam/Manipuri, so native Myanmar script is now
  force-resolved to `my` regardless of what `langid` guesses. Confirmed live
  after the fix: repeated native-Myanmar test inputs now consistently
  resolve to `my` and use this chain.
  - **Romanized/Latin-script Burmese ("Burglish") still translates
    unreliably** - confirmed on real examples, Gemma's output can diverge
    significantly from the intended meaning (e.g. translating a sentence
    about a movie as if it were about someone's appearance), and Googletrans
    does even worse on this exact text (misdetected the language entirely
    and barely translated at all). A genuine model-capability gap, not a
    routing bug - Burmese, unlike Hinglish, has no standardized Latin
    transliteration for either engine to have learned well. Googletrans is
    excluded from this chain automatically for romanized input anyway (see
    the hard exclusion rule below), so only Gemma is ever tried on it.
  - **Native Myanmar-script Burmese translates correctly** with Gemma (first
    in the chain above); confirmed Googletrans also handles it correctly
    when called directly, as the chain's fallback.
- **Googletrans is never used on romanized or mixed-script text, in any
  routing mode.** `language_router.py` drops it from the candidate chain
  outright (not just de-prioritized) whenever `script_type == "latin"` -
  this includes plain romanized text, code-mixed/Hinglish-style input, and
  even a manual `source_lang` override on text that's actually Latin script.
  Confirmed live: romanized Hindi and a manual `source_lang: "hi"` override
  on romanized text both correctly excluded `googletrans` from the chain and
  used Gemma alone.
- Previously, native Myanmar-script text was being misclassified as
  `"latin"` (romanized) because the Myanmar Unicode block (U+1000–U+109F)
  was missing from `_NATIVE_SCRIPT_RANGES` in `app/utils/script_detect.py`.
  Fixed by adding the Myanmar block and its two extension blocks.

## Run locally

```bash
# 1. Backend
pip install -r requirements.txt
redis-server &                      # or set TRANSLATE_CACHE_ENABLED=false
uvicorn app.main:app --reload

# 2. (optional, separate terminal, on your GPU host) IndicTrans2
cd indictrans_server && pip install -r requirements.txt && python app.py

# 3. Frontend
cd frontend && npm install && npm run dev
```

Then open http://localhost:5173 — this is Vite's dev-server port for
`npm run dev`, not the same as the Docker Compose deployment on port 9045
documented in "Live deployment" above. Use this local workflow when actively
developing the frontend; use the Docker deployment for anything else.

## Config

All backend tunables are env vars prefixed `TRANSLATE_` (see
`app/core/config.py`). Key ones you need to fill in:

| Variable | Why |
|---|---|
| `TRANSLATE_QWEN_BASE_URL` | Your docker inspect didn't show a published port — fill in once the container's running |
| `TRANSLATE_INDICTRANS_SERVICE_URL` | Where the IndicTrans2 microservice is running |

## Push to GitHub

```bash
cd translation_service
git init
git add .
git commit -m "Translation service: multi-model fallback pipeline + React console"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

`.gitignore` already excludes `node_modules/`, `venv/`, and `.env` files (so
your API keys etc. won't get committed) — double check `git status`
before your first push regardless.




