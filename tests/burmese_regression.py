import re

from app.utils.burmese_normalizer import detect_romanized_burmese, normalize_burmese_text, prepare_for_translation


def has_myanmar(text: str) -> bool:
    return bool(re.search(r"[\u1000-\u109F\uAA60-\uAA7F\uA9E0-\uA9FF]", text))


def test_romanized_burmese_cases():
    cases = [
        (
            "Yangon myo hma di nay lu oo yay a myar a pya su way khe kya de.",
            "ရန်ကုန်မြို့မှာ ဒီနေ့ လူဦးရေ အများအပြား စုဝေးခဲ့ကြတယ်။",
        ),
        (
            "Mat la se-khoun nga yat nay hma a si a wei pyu lote meh.",
            "မတ်လ ၁၅ ရက်နေ့မှာ အစည်းအဝေး ပြုလုပ်မယ်။",
        ),
        (
            "Telegram hma di tha din ko a myan sone phyant way nay kya de.",
            "Telegram မှာ ဒီသတင်းကို အမြန်ဆုံး ဖြန့်ဝေနေကြတယ်။",
        ),
        (
            "Thu do ga a-che-a-nay ko Facebook ne Telegram hnit khu lone hma mya way khe de.",
            "သူတို့က အခြေအနေကို Facebook နဲ့ Telegram နှစ်ခုလုံးမှာ မျှဝေခဲ့တယ်။",
        ),
        (
            "Tha din hte hma Ta-yote naing ngan, Myanmar naing ngan ne Htain naing ngan do ko phaw pya htar de.",
            "သတင်းထဲမှာ တရုတ်နိုင်ငံ၊ မြန်မာနိုင်ငံနဲ့ ထိုင်းနိုင်ငံတို့ကို ဖော်ပြထားတယ်။",
        ),
        (
            "di nay a yan pwe de",
            "ဒီနေ့အရမ်းပူတယ်။",
        ),
        (
            "a yan kaung de",
            "အရမ်းကောင်းတယ်။",
        ),
        (
            "ma kaung buu naw",
            "မကောင်းဘူးနော်။",
        ),
        (
            "hote tl",
            "ဟုတ်တယ်။",
        ),
        (
            "Lone-chone-yay a-che-a-nay kyaung lan a-choi ko pate htar par de.",
            "လမ်းအချို့ အခြေအနေကြောင့် ပိတ်ထားပါတယ်။",
        ),
    ]

    for raw, expected in cases:
        assert detect_romanized_burmese(raw), f"expected romanized Burmese detection for: {raw}"
        normalized = normalize_burmese_text(raw)
        assert has_myanmar(normalized), f"expected Myanmar script output for: {raw}"
        assert any(token in normalized for token in [
            "မြို့", "မှာ", "နိုင်ငံ", "Facebook", "Telegram", "တရုတ်", "မတ်လ", "ရက်",
            "သတင်း", "အရမ်း", "ဟုတ်", "မကောင်း", "နော်", "လမ်း", "အခြေအနေ", "ပိတ်"
        ]) or "ရန်ကုန်" in normalized


def test_native_burmese_passthrough():
    native = "ရန်ကုန်မြို့မှာ ဒီနေ့ လူဦးရေ အများအပြား စုဝေးခဲ့ကြတယ်။"
    assert normalize_burmese_text(native) == native


def test_burmese_preparation_before_cache_and_routing():
    raw = "Lone-chone-yay a-che-a-nay kyaung lan a-choi ko pate htar par de."
    prepared = prepare_for_translation(raw)
    assert prepared == "လမ်းအချို့အခြေအနေကြောင့်အချို့ကိုပိတ်ထားပါတယ်။"
    assert detect_romanized_burmese(raw)
    assert prepared != raw


def test_compressed_burmese_social_phrases():
    cases = [
        (
            "Di post ko lu a myar a pya ga mya way htar kya de.",
            "ဒီ post ကို လူအများအပြားက မျှဝေခဲ့တယ်။",
        ),
        (
            "ngar thwar meh",
            "ငါသွားမယ်။",
        ),
    ]
    for raw, expected in cases:
        prepared = prepare_for_translation(raw)
        assert expected.replace(" ", "") in prepared.replace(" ", ""), (
            f"expected normalized '{expected}' to be present in '{prepared}' for input '{raw}'"
        )


if __name__ == "__main__":
    test_romanized_burmese_cases()
    test_native_burmese_passthrough()
    test_burmese_preparation_before_cache_and_routing()
    test_compressed_burmese_social_phrases()
    print("burmese_regression checks passed")
