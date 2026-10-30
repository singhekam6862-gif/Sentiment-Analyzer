import json

import httpx
import pytest

from app.nlp import summarizer
from app.schemas import AspectKey, AspectScore, RawReview, ReviewStats, SentimentSplit

GOOD_ANSWER = {
    "pros": ["Deep bass", "Strong ANC in metro", "Paisa vasool price"],
    "cons": ["Weak outdoor mic", "Case scratches", "Battery fades after months"],
    "buying_verdict": "Great budget buds for music, not for calls.",
}

REVIEWS = [
    RawReview(review_id="fk_1", product_query="buds", rating=4, title="Mast", text="Bass is mast, ANC works in metro", review_date="2026-08-01"),
    RawReview(review_id="fk_2", product_query="buds", rating=2, text="Mic bakwas hai outdoors", review_date="2026-08-02"),
]

ASPECTS = [AspectScore(aspect=k, score=40 + 10 * i, summary="s") for i, k in enumerate(AspectKey)]

STATS = ReviewStats(
    overall_rating=3.8,
    sentiment_split=SentimentSplit(positive=60, negative=30, neutral=10),
    trust_score=72,
    verified_purchase_ratio=0.8,
    fulfillment_complaint_rate=20.0,
)


class FakeLLM:
    """Stands in for httpx.post; answers per provider URL and records every call."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        provider = "groq" if "groq.com" in url else "gemini"
        self.calls.append((provider, kwargs["json"]))
        answer = self.answers.get(provider)
        if isinstance(answer, Exception):
            raise answer
        content = answer if isinstance(answer, str) else json.dumps(answer)
        body = {"choices": [{"message": {"content": content}}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))


@pytest.fixture
def fake_llm(monkeypatch):
    def install(answers):
        fake = FakeLLM(answers)
        monkeypatch.setattr(summarizer.httpx, "post", fake)
        return fake

    return install


def test_no_keys_uses_rule_based_without_network(fake_llm):
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})
    summary = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert summary.generated_by == "rule_based"
    assert fake.calls == []


def test_groq_is_tried_first(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})

    summary = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert summary.generated_by == "groq"
    assert summary.pros == GOOD_ANSWER["pros"]
    assert [p for p, _ in fake.calls] == ["groq"]
    assert fake.calls[0][1]["model"] == "openai/gpt-oss-20b"
    assert "Mic bakwas hai outdoors" in fake.calls[0][1]["messages"][1]["content"]


def test_falls_through_to_gemini_when_groq_fails(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    fake = fake_llm({"groq": httpx.ConnectTimeout("slow"), "gemini": GOOD_ANSWER})

    summary = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert summary.generated_by == "gemini"
    assert [p for p, _ in fake.calls] == ["groq", "gemini"]


def test_provider_order_and_model_come_from_env(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("LLM_PROVIDERS", "gemini, groq")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    fake = fake_llm({"groq": GOOD_ANSWER, "gemini": GOOD_ANSWER})

    summary = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert summary.generated_by == "gemini"
    assert fake.calls[0][1]["model"] == "gemini-test-model"


def test_invalid_answers_fall_back_to_rule_based(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    fake_llm({"groq": "not json at all", "gemini": {"pros": ["only one"], "cons": [], "buying_verdict": "x"}})

    summary = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert summary.generated_by == "rule_based"


def test_valid_answer_is_cached(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    fake = fake_llm({"groq": GOOD_ANSWER})

    first = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)
    second = summarizer.generate_summary("Buds", REVIEWS, ASPECTS, STATS)

    assert first == second
    assert len(fake.calls) == 1


def test_no_trusted_reviews_skips_llm(monkeypatch, fake_llm):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    fake = fake_llm({"groq": GOOD_ANSWER})

    assert summarizer.generate_summary("Buds", [], ASPECTS, STATS).generated_by == "rule_based"
    assert fake.calls == []


@pytest.mark.parametrize(
    "raw, expected_pros",
    [
        (json.dumps(GOOD_ANSWER), GOOD_ANSWER["pros"]),
        (json.dumps({**GOOD_ANSWER, "pros": GOOD_ANSWER["pros"] + ["extra"]}), GOOD_ANSWER["pros"]),
        (json.dumps({**GOOD_ANSWER, "pros": ["a", " ", "b"]}), None),
        (json.dumps({**GOOD_ANSWER, "buying_verdict": ""}), None),
        (json.dumps({"pros": "abc"}), None),
        ("{broken", None),
    ],
    ids=["exact", "extra_trimmed", "blank_item", "empty_verdict", "missing_keys", "bad_json"],
)
def test_parse_llm_summary(raw, expected_pros):
    summary = summarizer.parse_llm_summary(raw, "groq")
    assert (summary.pros if summary else None) == expected_pros


def test_rule_based_summary_names_best_and_worst_aspects():
    summary = summarizer.build_rule_based_summary(ASPECTS, STATS)

    assert len(summary.pros) == 3 and len(summary.cons) == 3
    # ASPECTS scores rise with AspectKey order: value_for_money is best, sound_quality worst
    assert "strongest on value for money" in summary.buying_verdict
    assert "weakest on sound quality" in summary.buying_verdict
    assert "3.8/5" in summary.buying_verdict
