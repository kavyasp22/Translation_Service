# IndicTrans2 microservice

Serves `ai4bharat/indictrans2-indic-en-1B` (Indic → English) over HTTP so the
main translation service can call it like any other backend.

**This must be set up and run on your own GPU server.** I can't download the
weights for you - they're several GB and my sandbox has no network access to
huggingface.co. Below are the exact steps to run there.

## Setup

```bash
cd indictrans_server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

First run of `python app.py` downloads the model weights automatically from
HuggingFace into `~/.cache/huggingface` (make sure that machine has internet
access to huggingface.co and a few GB free). Subsequent runs load from cache.

## Run

```bash
python app.py
# serves on :8100 by default
```

Set `INDICTRANS_PORT` env var to change the port, and update
`TRANSLATE_INDICTRANS_SERVICE_URL` in the main service's `.env` to match if
you do.

## Test it directly

```bash
curl -X POST http://localhost:8100/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते, आप कैसे हैं?", "source_lang": "hi", "target_lang": "en"}'
```

## Limitations

- **Indic → English only.** This checkpoint can't translate the other
  direction. If you need English → Indic or Indic → Indic, load
  `ai4bharat/indictrans2-en-indic-1B` or `ai4bharat/indictrans2-indic-indic-1B`
  as a second model instance in `app.py` (same loading pattern, different
  checkpoint + target FLORES code) and add a route for it.
- **Supported source languages** are whatever's in `ISO_TO_FLORES` in
  `app.py` - currently hi, bn, as, pa, ne, ml, ur, gu, kn, mr, or, ta, te, mni.
  Extend that dict if you need more.
- Runs on GPU if available (`torch.cuda.is_available()`), otherwise falls
  back to CPU (much slower - fine for testing, not for production traffic).
