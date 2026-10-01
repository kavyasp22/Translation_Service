"""
test_indictrans.py — Test IndicTrans2 service on Chai_Tower (10.10.180.68:8200)

Run from any machine on the network:
    python test_indictrans.py
    python test_indictrans.py --url http://10.10.180.68:8200   # custom URL
    python test_indictrans.py --url http://localhost:8200       # if running locally
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# ── Config ─────────────────────────────────────────────────────────────────
DEFAULT_URL = "http://10.10.180.68:8200"

TEST_CASES = [
    # (source_lang, text, description)
    ("hi", "नमस्ते, आप कैसे हैं?",                        "Hindi  → English (greeting)"),
    ("ta", "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?",   "Tamil  → English (greeting)"),
    ("bn", "আমি ভালো আছি, ধন্যবাদ।",                      "Bengali → English (reply)"),
    ("ml", "നിങ്ങൾ എന്ത് ചെയ്യുന്നു?",                    "Malayalam → English (question)"),
    ("te", "మీరు ఎలా ఉన్నారు?",                           "Telugu → English (greeting)"),
    ("kn", "ನೀವು ಹೇಗಿದ್ದೀರಿ?",                           "Kannada → English (greeting)"),
    ("mr", "तुम्ही कसे आहात?",                            "Marathi → English (greeting)"),
    ("gu", "તમે કેમ છો?",                                  "Gujarati → English (greeting)"),
    ("pa", "ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ?",                            "Punjabi → English (greeting)"),
    ("ur", "آپ کیسے ہیں؟",                                 "Urdu   → English (greeting)"),
    # Multi-sentence stress test
    ("hi",
     "भारत एक विविधताओं से भरा देश है। यहाँ अनेक भाषाएँ बोली जाती हैं। "
     "हिंदी, तमिल, बांग्ला और मराठी प्रमुख भाषाओं में से हैं।",
     "Hindi  → English (multi-sentence)"),
]

# ── Helpers ─────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _post(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _hr(char: str = "─", width: int = 65) -> str:
    return char * width

# ── Tests ────────────────────────────────────────────────────────────────────
def test_health(base_url: str) -> bool:
    print(f"\n{BOLD}{'━'*65}{RESET}")
    print(f"{BOLD}  IndicTrans2 Service Test  →  {base_url}{RESET}")
    print(f"{BOLD}{'━'*65}{RESET}\n")

    print(f"{CYAN}[1/3] Health check ...{RESET}")
    try:
        t0     = time.time()
        result = _get(f"{base_url}/health")
        ms     = (time.time() - t0) * 1000
        status = result.get("status", "unknown")
        if status == "ok":
            print(f"  {GREEN}✅ /health → {result}  ({ms:.0f} ms){RESET}")
            return True
        else:
            print(f"  {YELLOW}⚠️  /health → {result}  (model may still be loading){RESET}")
            return False
    except urllib.error.URLError as e:
        print(f"  {RED}❌ Cannot reach {base_url}/health{RESET}")
        print(f"     Reason: {e.reason if hasattr(e,'reason') else e}")
        print(f"\n  Possible fixes:")
        print(f"    • Service not started  → ssh sherya@10.10.180.68 'sudo systemctl start indictrans2'")
        print(f"    • Firewall blocking    → ssh sherya@10.10.180.68 'sudo ufw allow 8200/tcp'")
        print(f"    • Wrong URL           → pass --url <correct-url>")
        return False

def test_translations(base_url: str) -> tuple[int, int]:
    print(f"\n{CYAN}[2/3] Translation tests ({len(TEST_CASES)} cases) ...{RESET}")
    passed = failed = 0
    timings = []

    for lang, text, desc in TEST_CASES:
        try:
            t0     = time.time()
            result = _post(
                f"{base_url}/translate",
                {"text": text, "source_lang": lang, "target_lang": "en"},
                timeout=40,
            )
            ms     = (time.time() - t0) * 1000
            timings.append(ms)
            translated = result.get("translated_text", "").strip()

            if translated:
                print(f"  {GREEN}✅{RESET} {desc}")
                print(f"       IN : {text[:60]}{'…' if len(text) > 60 else ''}")
                print(f"       OUT: {translated[:80]}{'…' if len(translated) > 80 else ''}")
                print(f"       ⏱  {ms:.0f} ms")
                passed += 1
            else:
                print(f"  {YELLOW}⚠️{RESET}  {desc} — empty response ({ms:.0f} ms)")
                failed += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            print(f"  {RED}❌{RESET} {desc} — HTTP {e.code}: {body[:120]}")
            failed += 1
        except Exception as e:
            print(f"  {RED}❌{RESET} {desc} — {e}")
            failed += 1
        print()

    if timings:
        avg = sum(timings) / len(timings)
        print(f"  {_hr()}")
        print(f"  ⏱  Avg latency: {avg:.0f} ms  |  Min: {min(timings):.0f} ms  |  Max: {max(timings):.0f} ms")

    return passed, failed

def test_error_handling(base_url: str):
    print(f"\n{CYAN}[3/3] Error handling tests ...{RESET}")

    # Bad source lang
    try:
        result = _post(f"{base_url}/translate",
                       {"text": "hello", "source_lang": "xx", "target_lang": "en"})
        print(f"  {YELLOW}⚠️{RESET}  Bad lang code — unexpected 200: {result}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print(f"  {GREEN}✅{RESET} Bad source_lang → 400 Bad Request (correct)")
        else:
            print(f"  {YELLOW}⚠️{RESET}  Bad source_lang → HTTP {e.code}")

    # Wrong target lang (this model is indic→en only)
    try:
        result = _post(f"{base_url}/translate",
                       {"text": "नमस्ते", "source_lang": "hi", "target_lang": "fr"})
        print(f"  {YELLOW}⚠️{RESET}  Wrong target_lang — unexpected 200: {result}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print(f"  {GREEN}✅{RESET} Wrong target_lang (fr) → 400 Bad Request (correct)")
        else:
            print(f"  {YELLOW}⚠️{RESET}  Wrong target_lang → HTTP {e.code}")

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Test IndicTrans2 microservice")
    parser.add_argument("--url", default=DEFAULT_URL,
                        help=f"Base URL of the service (default: {DEFAULT_URL})")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    healthy = test_health(base_url)
    if not healthy:
        print(f"\n{RED}Service is not healthy — skipping translation tests.{RESET}\n")
        sys.exit(1)

    passed, failed = test_translations(base_url)
    test_error_handling(base_url)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'━'*65}{RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}  ALL {total}/{total} TESTS PASSED ✅{RESET}")
        print(f"  Service at {base_url} is fully operational and offline-ready.")
    else:
        print(f"{YELLOW}{BOLD}  {passed}/{total} PASSED, {failed} FAILED ⚠️{RESET}")
    print(f"{BOLD}{'━'*65}{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
