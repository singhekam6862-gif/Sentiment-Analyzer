import json

import httpx
import pytest

from app.nlp import summarizer
from app.schemas import Aspect, Quote, UseCase

GOOD_ANSWER = {
    "headline": "Great budget buds for music, not for calls.",
    "pros": [{"text": "Deep bass", "aspect": "sound_quality"}],
    "cons": [{"text": "Weak outdoor mic", "aspect": "mic_call_quality"}],
}

ASPECTS = [
    Aspect(key="sound_quality", label="Sound quality", praise=5, complaints=1, mixed=0, confidence="medium",
           quotes=[Quote(review_id="fk_1", text="Bass is mast", polarity="praise")]),
    Aspect(key="mic_call_quality", label="Calls and mic", praise=0, complaints=2, mixed=0, confidence="low",
           quotes=[Quote(review_id="fk_2", text="Mic bakwas hai outdoors", polarity="complaint")]),
]
USES = [UseCase(name="Music", verdict="good", reason="r", review_count=6)]


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")


def test_no_keys_returns_none_without_network(fake_llm):
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})
    assert summarizer.generate_summary("Buds", ASPECTS, USES) is None
    assert fake.calls == []


def test_groq_is_tried_first(keys, fake_llm):
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})

    draft = summarizer.generate_summary("Buds", ASPECTS, USES)

    assert draft.generated_by == "groq"
    assert draft.pros == [("Deep bass", "sound_quality")]
    assert [p for p, _ in fake.calls] == ["groq"]
    assert fake.calls[0][1]["model"] == "openai/gpt-oss-20b"
    prompt = fake.calls[0][1]["messages"][1]["content"]
    assert "Mic bakwas hai outdoors" in prompt and "Music: good" in prompt


def test_falls_through_to_gemini_when_groq_fails(keys, fake_llm):
    fake = fake_llm({"groq": httpx.ConnectTimeout("slow"), "gemini": GOOD_ANSWER})
    assert summarizer.generate_summary("Buds", ASPECTS, USES).generated_by == "gemini"
    assert [p for p, _ in fake.calls] == ["groq", "gemini"]


def test_provider_order_and_model_come_from_env(keys, monkeypatch, fake_llm):
    monkeypatch.setenv("LLM_PROVIDERS", "gemini, groq")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})

    assert summarizer.generate_summary("Buds", ASPECTS, USES).generated_by == "gemini"
    assert fake.calls[0][1]["model"] == "gemini-test-model"


def test_invalid_answers_return_none(keys, fake_llm):
    fake_llm({"groq": "not json at all", "gemini": {"pros": []}})
    assert summarizer.generate_summary("Buds", ASPECTS, USES) is None


def test_valid_answer_is_cached(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    fake = fake_llm({"groq": GOOD_ANSWER})

    first = summarizer.generate_summary("Buds", ASPECTS, USES)
    second = summarizer.generate_summary("Buds", ASPECTS, USES)

    assert first == second
    assert len(fake.calls) == 1


def test_no_aspects_skips_llm(keys, fake_llm):
    fake = fake_llm({"groq": GOOD_ANSWER})
    assert summarizer.generate_summary("Buds", [], USES) is None
    assert fake.calls == []


@pytest.mark.parametrize(
    "raw, expected_pros",
    [
        (json.dumps(GOOD_ANSWER), [("Deep bass", "sound_quality")]),
        (json.dumps({**GOOD_ANSWER, "pros": [{"text": "Made up", "aspect": "price_drop"}]}), []),
        (json.dumps({**GOOD_ANSWER, "pros": [{"text": " ", "aspect": "sound_quality"}]}), []),
        (json.dumps({**GOOD_ANSWER, "headline": ""}), None),
        (json.dumps({**GOOD_ANSWER, "headline": "word " * 19}), None),
        (json.dumps({"pros": "abc"}), None),
        ("{broken", None),
    ],
    ids=["valid", "unknown_aspect_dropped", "blank_dropped", "empty_headline", "long_headline", "missing_keys", "bad_json"],
)
def test_parse_llm_summary(raw, expected_pros):
    draft = summarizer.parse_llm_summary(raw, "groq", {"sound_quality", "mic_call_quality"})
    assert (draft.pros if draft else None) == expected_pros


LONG_TITLE = "Dot Key Vitamin C E Sorbet Super Bright Moisturizer Face Reduces Skin Dullness"


def test_short_name_comes_from_the_llm(keys, fake_llm):
    fake_llm({"groq": {"name": "Dot Key Vitamin C E Sorbet Moisturizer"}})
    assert summarizer.short_product_name(LONG_TITLE) == "Dot Key Vitamin C E Sorbet Moisturizer"


@pytest.mark.parametrize(
    "answer",
    [{"name": "Dot Key Glow Cream"}, {"name": "Dot Key Vitamin C E Sorbet Super Bright Moisturizer"}, {"name": ""},
     {"name": 5}, {"other": "x"}, ["x"], "not json"],
    ids=["invented_word", "too_long", "empty", "not_text", "no_name", "not_object", "not_json"],
)
def test_bad_short_name_falls_back_to_first_words(keys, fake_llm, answer):
    fake_llm(lambda _provider, _body: answer)
    assert summarizer.short_product_name(LONG_TITLE) == "Dot Key Vitamin C E"


def test_short_name_without_keys_cuts_before_the_specs(fake_llm):
    fake = fake_llm({})
    assert summarizer.short_product_name("Acme Tab 5 Pro - (8 GB/128 GB) Wi-Fi Tablet Grey") == "Acme Tab 5 Pro"
    assert summarizer.short_product_name("Acme Tab 5 Pro Max (8 GB) Tablet") == "Acme Tab 5 Pro Max"
    assert fake.calls == []


def test_short_titles_skip_the_llm(keys, fake_llm):
    fake = fake_llm({"groq": {"name": "x"}})
    assert summarizer.short_product_name("realme Buds T310") == "realme Buds T310"
    assert fake.calls == []
