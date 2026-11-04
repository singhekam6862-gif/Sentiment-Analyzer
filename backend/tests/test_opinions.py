import json

import pytest

from app.nlp import opinions
from app.nlp.analysis import analyse
from app.schemas import Product, RawReview


def review(rid: str, text: str, rating: int = 4) -> RawReview:
    return RawReview(review_id=rid, product_query="phone", rating=rating, text=text, review_date="2026-09-01",
                     verified_purchase=True)


PHONE = [
    review("p1", "Camera is mast in daylight but battery drains by evening.", 3),
    review("p2", "Display is bahut sharp. Camera is decent.", 5),
    review("p3", "After 2 months the speaker stopped working.", 1),
]

OPINIONS = {
    "p1": [{"aspect": "Camera", "polarity": "praise", "quote": "Camera is mast in daylight"},
           {"aspect": "battery_life", "polarity": "complaint", "quote": "battery drains by evening"}],
    "p2": [{"aspect": "display", "polarity": "praise", "quote": "Display is bahut sharp"},
           {"aspect": "camera", "polarity": "mixed", "quote": "Camera is decent"}],
    "p3": [{"aspect": "long_term_reliability", "polarity": "complaint", "quote": "After 2 months the speaker stopped working"}],
}


def answer_for(prompt: str, table: dict = OPINIONS) -> dict:
    """Answers only for the review ids present in this batch's prompt."""
    return {"reviews": [{"id": rid, "opinions": ops} for rid, ops in table.items() if f"[{rid}]" in prompt]}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")


def test_parse_keeps_only_verbatim_valid_units():
    batch = {r.review_id: r for r in PHONE[:1]}
    raw = json.dumps({"reviews": [
        {"id": "p1", "opinions": [
            {"aspect": "Camera ", "polarity": "praise", "quote": "“Camera is mast in daylight”"},
            {"aspect": "camera", "polarity": "complaint", "quote": "battery drains by evening"},  # duplicate aspect
            {"aspect": "battery_life", "polarity": "complaint", "quote": "battery dies by night"},  # not verbatim
            {"aspect": "charging", "polarity": "angry", "quote": "battery drains by evening"},  # bad polarity
        ]},
        {"id": "unknown", "opinions": [{"aspect": "x", "polarity": "praise", "quote": "y"}]},
    ]})
    assert opinions.parse_opinions(raw, batch) == {"p1": [("camera", "praise", "Camera is mast in daylight")]}


@pytest.mark.parametrize("raw", ["{broken", json.dumps({"opinions": []}), json.dumps({"reviews": "x"})])
def test_parse_rejects_malformed_answers(raw):
    assert opinions.parse_opinions(raw, {r.review_id: r for r in PHONE}) is None


def test_without_keys_uses_rules_and_no_network(fake_llm):
    fake = fake_llm({"groq": {}})
    found = opinions.extract_all_opinions(PHONE, ["long_term_reliability"])
    assert fake.calls == []
    assert ("long_term_reliability", "complaint", "After 2 months the speaker stopped working") in found["p3"]


def test_llm_units_are_used_and_keys_carry_to_later_batches(keys, fake_llm, monkeypatch):
    monkeypatch.setattr(opinions, "BATCH_SIZE", 2)
    fake = fake_llm(lambda _provider, body: answer_for(body["messages"][1]["content"]))

    found = opinions.extract_all_opinions(PHONE, ["long_term_reliability"])

    assert len(fake.calls) == 2
    assert found["p2"] == [("display", "praise", "Display is bahut sharp"), ("camera", "mixed", "Camera is decent")]
    second_prompt = fake.calls[1][1]["messages"][1]["content"]
    assert "camera" in second_prompt.splitlines()[0] and "display" in second_prompt.splitlines()[0]


def test_a_failed_batch_falls_back_to_rules(keys, fake_llm):
    fake_llm({"groq": "not json"})
    found = opinions.extract_all_opinions(PHONE, [])
    assert found["p3"] == opinions.extract_opinions(PHONE[2])


def test_any_category_gets_its_own_aspects(keys, fake_llm):
    """A phone has no template: aspects come from the LLM, quotes stay verbatim, use cases are empty."""
    def answer(_provider, body):
        if "opinion units" in body["messages"][0]["content"]:
            return answer_for(body["messages"][1]["content"])
        return {"headline": "Sharp screen, weak battery.", "pros": [{"text": "Sharp display", "aspect": "display"}], "cons": []}

    fake_llm(answer)
    product = Product(id="p", name="Acme Phone 5G", category="Smartphones", source_url=None,
                      data_source="catalogue", collected_on=None)
    result = analyse(product, PHONE)

    labels = {a.key: a.label for a in result.aspects}
    assert labels["camera"] == "Camera" and labels["display"] == "Display"
    assert result.use_cases == []
    texts = {r.review_id: r.text for r in result.reviews}
    assert all(q.text in texts[q.review_id] for a in result.aspects for q in a.quotes)
    assert result.verdict.generated_by == "groq"
    assert result.pros[0].review_ids == ["p2"]
