from app.utils.abbreviation_normalizer import expand_common_english_abbreviations
from app.utils.lang_codes import normalize_language_code


def test_expand_english_abbreviations():
    assert expand_common_english_abbreviations("pls reply") == "please reply"
    assert expand_common_english_abbreviations("plz call me ASAP") == "please call me as soon as possible"
    assert expand_common_english_abbreviations("msg me bcoz u r late") == "message me because you are late"
    assert expand_common_english_abbreviations("नमस्ते pls") == "नमस्ते please"
    assert expand_common_english_abbreviations("I am fine") == "I am fine"


def test_multilingual_shortcuts_are_expanded():
    assert expand_common_english_abbreviations("kya hua") == "kya hua"
    assert expand_common_english_abbreviations("nahi hoga") == "nahin hoga"
    assert expand_common_english_abbreviations("chalo movie") == "chalo movie"
    assert expand_common_english_abbreviations("xie xie bhai") == "xie xie brother / friend"
    assert expand_common_english_abbreviations("accha ok") == "accha ok"
    assert expand_common_english_abbreviations("hun sahi hai") == "hun sahi hai"


def test_normalize_language_aliases():
    assert normalize_language_code("en") == "en"
    assert normalize_language_code("ENG") == "en"
    assert normalize_language_code("english") == "en"
    assert normalize_language_code("bn") == "bn"
    assert normalize_language_code("bengali") == "bn"
    assert normalize_language_code("Bengal") == "bn"
    assert normalize_language_code("hi") == "hi"
    assert normalize_language_code("Hindi") == "hi"
    assert normalize_language_code("hin") == "hi"
    assert normalize_language_code("my") == "my"
    assert normalize_language_code("myanmar") == "my"
    assert normalize_language_code("mya") == "burmese"
    assert normalize_language_code("burmese") == "burmese"
    assert normalize_language_code("zh-cn") == "zh"
    assert normalize_language_code("zh_tw") == "zh"
    assert normalize_language_code("romanized/mixed") == "mix"
    assert normalize_language_code("mixed") == "mix"
    assert normalize_language_code("multilingual") == "mix"
    assert normalize_language_code("hinglish") == "mix"
    assert normalize_language_code("ar") == "ar"
    assert normalize_language_code("arabic") == "ar"
    assert normalize_language_code("dhivehi") == "dv"
    assert normalize_language_code("maldivian") == "dv"
    assert normalize_language_code("pashto") == "ps"
    assert normalize_language_code("balochi") == "bal"
    assert normalize_language_code("northern sotho") == "nso"
    assert normalize_language_code("kinyarwanda") == "rw"
    assert normalize_language_code("shona") == "sn"
    assert normalize_language_code("haitian creole") == "mix"
    assert normalize_language_code("unknown") == "und"
    assert normalize_language_code("   ") == "und"
    assert normalize_language_code(None) == "und"
