"""
Quick manual smoke test - not a full pytest suite, just something to run once
the service is up to sanity-check the routing decisions.

Run: python tests/smoke_test.py  (with the service running on localhost:8000)
"""
import httpx

CASES = [
    {"text": "नमस्ते, आप कैसे हैं?", "expect_route": "native_script_high_confidence"},
    {"text": "aj PM Modi ne BRICS summit me participate kiya", "expect_route": "romanized_or_mixed"},
    {"text": "Hello, how are you?", "expect_route": "latin_english"},
]


def main():
    for case in CASES:
        resp = httpx.post(
            "http://localhost:8048/translate",
            json={"text": case["text"], "source_lang": "auto", "target_lang": "en"},
            timeout=30,
        )
        data = resp.json()
        print(f"\nInput: {case['text']}")
        print(f"  route_reason: {data.get('route_reason')} (expected ~{case['expect_route']})")
        print(f"  model_used:   {data.get('model_used')}")
        print(f"  translated:   {data.get('translated_text')}")
        print(f"  latency_ms:   {data.get('latency_ms')}")


if __name__ == "__main__":
    main()
