"""
Standalone microservice for ai4bharat/indictrans2-indic-en-1B.

WHY SEPARATE FROM THE MAIN SERVICE:
  - Different dependency stack (torch, transformers, IndicTransToolkit) that
    would otherwise bloat/conflict with the main API's lightweight deps.
  - Needs its own GPU memory allocation, separate from the vLLM servers
    already running Gemma and Qwen.
  - Different serving pattern entirely: encoder-decoder .generate() with
    IndicProcessor pre/post-processing, not an OpenAI-style chat call.

SETUP (run on your GPU server - NOT something that can be downloaded/run
inside a sandboxed dev environment; the weights are several GB):

    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    # first run downloads ~2-4GB of weights from huggingface.co and caches
    # them under ~/.cache/huggingface - make sure that machine has internet
    # access and enough disk space
    python app.py
    # serves on :8100 by default (matches TRANSLATE_INDICTRANS_SERVICE_URL
    # in the main service's config)

LIMITATION: this checkpoint only translates INDIC -> ENGLISH. It will reject
any request where target_lang != "en". If you also need English -> Indic or
Indic -> Indic, load ai4bharat/indictrans2-en-indic-1B or
ai4bharat/indictrans2-indic-indic-1B as additional model instances following
the same pattern (see AI4Bharat's IndicTrans2 GitHub repo for those
checkpoint names) and add routes/branches for them below.
"""
import logging
import os
import threading

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("indictrans2")

MODEL_NAME = os.environ.get("INDICTRANS_MODEL", "ai4bharat/indictrans2-indic-en-1B")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PORT = int(os.environ.get("INDICTRANS_PORT", "8200"))
# Both directly drive GPU memory/compute per generate() call - confirmed
# live these (not the ~1.1B model weights themselves, ~2.2GB in fp16) are
# why this service was using ~12.7GB. num_beams=5 tracks 5 candidate
# translations per input simultaneously (~5x the generation cost of greedy
# decoding); BATCH_SIZE=16 holds that many inputs' worth of activations at
# once. Lowered to reduce contention with Gemma on this shared GPU, at a
# small, generally modest cost to translation quality (beam search still
# runs, just with less breadth) - see indictrans_server/README.md if
# quality regressions are ever reported and this needs revisiting.
NUM_BEAMS = int(os.environ.get("INDICTRANS_NUM_BEAMS", "2"))
BATCH_SIZE = int(os.environ.get("INDICTRANS_BATCH_SIZE", "8"))

# ISO-639-1-ish codes (what the main service sends) -> FLORES-200 codes
# (what IndicTrans2 / IndicProcessor expects). Extend as needed - see
# app/utils/lang_codes.py in the main service for the same mapping.
ISO_TO_FLORES = {
    "hi": "hin_Deva", "bn": "ben_Beng", "as": "asm_Beng", "pa": "pan_Guru",
    "ne": "npi_Deva", "ml": "mal_Mlym", "ur": "urd_Arab", "gu": "guj_Gujr",
    "kn": "kan_Knda", "mr": "mar_Deva", "or": "ory_Orya", "ta": "tam_Taml",
    "te": "tel_Telu", "mni": "mni_Beng",
}
TARGET_FLORES = "eng_Latn"  # this checkpoint only outputs English

app = FastAPI(title="IndicTrans2 Microservice")

_model = None
_tokenizer = None
_processor = None

# /translate runs as a sync `def` route, which FastAPI/Starlette executes in
# a shared thread pool - without this, concurrent requests (from multiple
# pipeline workers, or multiple chunks of one document) each call
# _model.generate() at the same time on this one shared model instance/GPU.
# Confirmed live: that caused the whole service to hang - including health
# checks, which don't even touch the model - requiring a hard process
# restart to recover. This lock guarantees only one generate() call (and its
# surrounding tokenize/pre/post-process steps, since the tokenizer and
# processor are also shared, mutable objects) runs at a time, regardless of
# how many requests arrive concurrently.
_generate_lock = threading.Lock()


class TranslateRequest(BaseModel):
    text: str
    source_lang: str  # ISO code, e.g. "hi" - "auto" is NOT supported, must be known
    target_lang: str = "en"


class TranslateResponse(BaseModel):
    translated_text: str


@app.on_event("startup")
def load_model():
    global _model, _tokenizer, _processor
    from IndicTransToolkit.processor import IndicProcessor  # local import: only needed here

    logger.info(f"Loading {MODEL_NAME} on {DEVICE} ...")
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    _model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    ).to(DEVICE)
    _model.eval()
    _processor = IndicProcessor(inference=True)
    logger.info("IndicTrans2 model loaded and ready.")


def _count_tokens(text_segment: str, tokenizer=None, src_lang: str = None) -> int:
    if tokenizer is not None:
        try:
            if src_lang:
                tokenizer.src_lang = src_lang
            return len(tokenizer.encode(text_segment, add_special_tokens=False))
        except Exception:
            return int(len(text_segment.split()) * 1.5) + 1
    return int(len(text_segment.split()) * 1.5) + 1


def split_text_into_meaningful_chunks(text: str, max_tokens: int = 180, tokenizer=None, src_lang: str = None) -> list[str]:
    """
    Splits input text into meaningful sentence chunks to guarantee IndicTrans2
    does not truncate multi-sentence inputs or stop early at punctuation.
    """
    import re
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    atomic_units = []
    for para in paragraphs:
        # Sentence splitting pattern including Indic sentence danda (।), double danda (॥), ., !, ?
        sentences = re.split(r"(?<=[।॥.!?])\s+", para)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if _count_tokens(sentence, tokenizer) <= max_tokens:
                atomic_units.append(sentence)
            else:
                # Split long sentence by clause markers (,, ;, :, —, -)
                clauses = re.split(r"(?<=[,;:—-])\s+", sentence)
                for clause in clauses:
                    clause = clause.strip()
                    if not clause:
                        continue
                    if _count_tokens(clause, tokenizer) <= max_tokens:
                        atomic_units.append(clause)
                    else:
                        # Split by space (words) to guarantee NO word truncation
                        words = clause.split()
                        current_word_chunk = []
                        for word in words:
                            test_chunk = " ".join(current_word_chunk + [word])
                            if current_word_chunk and _count_tokens(test_chunk, tokenizer) > max_tokens:
                                atomic_units.append(" ".join(current_word_chunk))
                                current_word_chunk = [word]
                            else:
                                current_word_chunk.append(word)
                        if current_word_chunk:
                            atomic_units.append(" ".join(current_word_chunk))

    return atomic_units


@app.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    if req.target_lang != "en":
        raise HTTPException(
            status_code=400,
            detail="This checkpoint (indic-en-1B) only supports target_lang='en'",
        )
    if req.source_lang not in ISO_TO_FLORES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source_lang '{req.source_lang}'. "
                   f"Supported: {list(ISO_TO_FLORES.keys())}",
        )

    src_flores = ISO_TO_FLORES[req.source_lang]

    chunks = split_text_into_meaningful_chunks(req.text, max_tokens=180, tokenizer=_tokenizer, src_lang=src_flores)
    if not chunks:
        return TranslateResponse(translated_text="")

    translated_chunks = []
    for i in range(0, len(chunks), BATCH_SIZE):
        sub_batch = chunks[i : i + BATCH_SIZE]
        try:
            with _generate_lock:
                batch = _processor.preprocess_batch(sub_batch, src_lang=src_flores, tgt_lang=TARGET_FLORES)
                inputs = _tokenizer(batch, truncation=True, padding="longest", return_tensors="pt").to(DEVICE)

                with torch.no_grad():
                    generated_tokens = _model.generate(
                        **inputs,
                        use_cache=True,
                        min_length=0,
                        max_length=256,
                        num_beams=NUM_BEAMS,
                        num_return_sequences=1,
                    )

                decoded = _tokenizer.batch_decode(
                    generated_tokens.detach().cpu().tolist(),
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=True,
                )

                translations = _processor.postprocess_batch(decoded, lang=TARGET_FLORES)
            translated_chunks.extend(translations)
        except torch.cuda.OutOfMemoryError as e:
            # This GPU is shared with other models (Gemma reserves a large
            # static fraction of it) - fail this request loudly and clear
            # the allocator's cache so a bad allocation here doesn't leave
            # the process in a degraded state for the NEXT request. Confirmed
            # live: without this, a request that hit OOM left the service
            # answering nothing at all - including health checks - for every
            # request after it, requiring a hard process restart.
            logger.error(f"CUDA OOM on batch {i // BATCH_SIZE} ({len(sub_batch)} chunks): {e}")
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            raise HTTPException(
                status_code=503,
                detail="IndicTrans2 ran out of GPU memory for this request "
                       "(the GPU is shared with other models) - try again or "
                       "with shorter text.",
            )
        except Exception as e:
            logger.error(f"Translation failed on batch {i // BATCH_SIZE} ({len(sub_batch)} chunks): {e}")
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            raise HTTPException(status_code=500, detail=f"Translation failed: {e}")

    full_translation = " ".join(translated_chunks)
    return TranslateResponse(translated_text=full_translation)


@app.get("/health")
def health():
    return {"status": "ok" if _model is not None else "loading"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
